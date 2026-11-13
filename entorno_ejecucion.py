"""UTF-8, confianza HTTPS y diagnósticos de transporte; sin lógica financiera."""
from __future__ import annotations
import atexit
import ctypes
import hashlib
import os
from pathlib import Path
import re
import shutil
import ssl
import sys
import threading
import uuid

CA_VARIABLES = ('REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'SSL_CERT_FILE')
_LOCK = threading.RLock()


class RuntimeConfigurationError(RuntimeError):
    pass


def child_environment(env=None):
    """Python consulta estas variables al nacer; text=True por sí solo no basta."""
    return {**(os.environ if env is None else env),
            'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}


def _validated_bundle(path):
    try:
        data = Path(path).read_bytes()
        certificates = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data, re.S)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=b'\n'.join(certificates).decode('ascii'))
        if not context.cert_store_stats()['x509_ca']:
            raise ValueError('El PEM no contiene autoridades certificadoras')
        return data
    except (OSError, ValueError, ssl.SSLError) as exc:
        raise RuntimeConfigurationError(f'CA_LOCAL: certificado CA ausente o inválido: {path}') from exc


def _short_path(path):
    """Alias nativo 8.3, si Windows lo ofrece; nunca se presupone que exista."""
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    get_short = kernel.GetShortPathNameW
    get_short.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    get_short.restype = w.DWORD
    size = get_short(str(path), None, 0)
    if not size:
        return None
    buf = ctypes.create_unicode_buffer(size)
    if not get_short(str(path), buf, size):
        return None
    return Path(buf.value) if buf.value.isascii() else None


def _private_ascii_directory():
    """Crea atómicamente una carpeta Windows con DACL protegida usuario/SYSTEM.

    No usa una carpeta común preexistente para guardar la CA. La ACL forma
    parte de CreateDirectoryW: no existe una ventana con permisos heredados.
    """
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    token = w.HANDLE(); size = w.DWORD(); sid = w.LPWSTR(); descriptor = ctypes.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        buf = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid_pointer = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid)):
            raise ctypes.WinError(ctypes.get_last_error())
        sddl = f'O:{sid.value}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{sid.value})'
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise ctypes.WinError(ctypes.get_last_error())

        class SecurityAttributes(ctypes.Structure):
            _fields_ = [('length', w.DWORD), ('descriptor', ctypes.c_void_p), ('inherit', w.BOOL)]

        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, ctypes.POINTER(SecurityAttributes)]
        shell.SHGetFolderPathW.argtypes = [w.HWND, ctypes.c_int, w.HANDLE, w.DWORD, w.LPWSTR]
        kernel.GetWindowsDirectoryW.argtypes = [w.LPWSTR, w.UINT]
        common = ctypes.create_unicode_buffer(32768); windows = ctypes.create_unicode_buffer(32768)
        roots = []
        if shell.SHGetFolderPathW(None, 0x23, None, 0, common) == 0:  # ProgramData
            roots.append(Path(common.value))
        if kernel.GetWindowsDirectoryW(windows, len(windows)):
            roots.append(Path(windows.value) / 'Temp')
        for root in roots:
            root = root if str(root).isascii() else _short_path(root)
            if root is None:
                continue
            path = root / ('vb-ca-' + uuid.uuid4().hex)
            if kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
                atexit.register(shutil.rmtree, path, ignore_errors=True)
                return path
        raise RuntimeConfigurationError('CA_LOCAL: Windows no permite crear una carpeta ASCII privada para el certificado; no se desactiva HTTPS')
    finally:
        if descriptor.value: kernel.LocalFree(descriptor)
        if sid: kernel.LocalFree(ctypes.cast(sid, ctypes.c_void_p))
        if token: kernel.CloseHandle(token)


def _ascii_bundle(source):
    source = Path(source).absolute()
    data = _validated_bundle(source)
    if str(source).isascii():
        return str(source)
    alias = _short_path(source)
    if alias and _validated_bundle(alias) == data:
        return str(alias)
    directory = _private_ascii_directory()
    destination = directory / 'ca.pem'
    # O_EXCL y DACL heredada de la carpeta privada; no se reutilizan archivos ajenos.
    with destination.open('xb') as stream:
        stream.write(data)
    if hashlib.sha256(_validated_bundle(destination)).digest() != hashlib.sha256(data).digest():
        raise RuntimeConfigurationError('CA_LOCAL: integridad del certificado copiado no coincide')
    return str(destination)


def _configure_windows_ca(environ):
    import certifi
    selected = next((environ[key] for key in CA_VARIABLES if environ.get(key)), certifi.where())
    converted = {}
    settings = {}
    for key in CA_VARIABLES:
        source = environ.get(key) or selected
        if source not in converted:
            try:converted[source] = _ascii_bundle(source)
            except OSError as exc:
                raise RuntimeConfigurationError('CA_LOCAL: no se pudo preparar el certificado con permisos seguros; HTTPS sigue siendo obligatorio') from exc
        settings[key] = converted[source]
    # Aplicación atómica después de validar todos los bundles explícitos.
    environ.update(settings)
    return settings


def configure_utf8():
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    for name in ('stdin', 'stdout', 'stderr'):
        stream = getattr(sys, name, None)
        if hasattr(stream, 'reconfigure') and str(getattr(stream, 'encoding', '')).lower().replace('-', '') != 'utf8':
            stream.reconfigure(encoding='utf-8', errors='strict' if name == 'stdin' else 'backslashreplace')


def configure_runtime():
    with _LOCK:
        configure_utf8()
        # Linux/Streamlit Cloud conservan sus CA/proxy heredados, incluidos CA corporativos.
        if sys.platform == 'win32':
            _configure_windows_ca(os.environ)


def network_diagnostic(error, provider):
    """Clasifica transporte sin convertirlo en dato contable ni exponer cabeceras."""
    response = getattr(error, 'response', None)
    status = getattr(response, 'status_code', None)
    code = getattr(error, 'code', None)
    name = type(error).__name__.lower()
    detail = str(error).lower()
    if code == 77 or 'curl: (77)' in detail:
        kind, message = 'CA_LOCAL', 'No se pudo abrir el almacén CA; revisar instalación/certificados'
    elif isinstance(error, ssl.SSLError) or 'ssl' in name or code in (35, 58, 60) or 'certificate verify failed' in detail:
        kind, message = 'SSL', 'No se pudo verificar o negociar HTTPS; no se desactiva la verificación'
    elif status == 429 or 'ratelimit' in name:
        kind, message = 'LIMITE_YAHOO' if provider == 'Yahoo' else 'HTTP_429', 'Límite de solicitudes; reintentar más tarde'
    elif status == 403:
        kind, message = 'SEC_HTTP_403' if provider == 'SEC' else 'HTTP_403', 'El servidor deniega el acceso; no es un error de certificados'
    elif 'timeout' in name or code == 28:
        kind, message = 'RED_TIMEOUT', 'Tiempo de conexión agotado'
    elif 'connection' in name or code in (5, 6, 7, 52, 56):
        kind, message = 'RED_CONEXION', 'No se pudo conectar con el proveedor'
    elif isinstance(error, (ValueError, KeyError, TypeError)):
        kind, message = 'DATOS_INCOMPLETOS', 'Respuesta ausente, incompleta o incompatible; no se inventan datos'
    else:
        kind, message = 'PROVEEDOR', type(error).__name__
    return f'[{kind}] {provider}: {message}'
