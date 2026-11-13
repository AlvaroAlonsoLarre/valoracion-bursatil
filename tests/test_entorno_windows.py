"""Transporte real local y compatibilidad de infraestructura, sin datos inventados."""
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import threading
from types import SimpleNamespace
import certifi
import pytest
import requests
import entorno_ejecucion as runtime

ROOT = Path(__file__).resolve().parents[1]
TLS = Path(__file__).parent / 'fixtures/tls_local'


def test_child_utf8_io_and_files_in_unicode_directory(tmp_path):
    folder=tmp_path/'Álvaro 日本 & !';folder.mkdir()
    script=folder/'prueba.py'
    script.write_text("from entorno_ejecucion import configure_runtime\nconfigure_runtime()\nimport json,sys\np=json.load(sys.stdin)\nprint('− × á 日本 '+p['dato'])\nprint('advertencia −',file=sys.stderr)\n",encoding='utf-8')
    env=runtime.child_environment({**os.environ,'PYTHONUTF8':'0','PYTHONIOENCODING':'cp1252','PYTHONPATH':str(ROOT)})
    proc=subprocess.run([sys.executable,str(script)],input=json.dumps({'dato':'acción'},ensure_ascii=False),
                        env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert proc.returncode==0 and '− × á 日本 acción' in proc.stdout and 'advertencia −' in proc.stderr
    assert env['PYTHONUTF8']=='1' and env['PYTHONIOENCODING']=='utf-8'


def test_unicode_ca_copy_has_identical_bytes_and_rejects_tampering(tmp_path,monkeypatch):
    source=tmp_path/'José 日本.pem';source.write_bytes(Path(certifi.where()).read_bytes())
    private=tmp_path/'private';private.mkdir()
    monkeypatch.setattr(runtime,'_short_path',lambda path:None)
    monkeypatch.setattr(runtime,'_private_ascii_directory',lambda:private)
    target=Path(runtime._ascii_bundle(source))
    assert str(target).isascii() and target.read_bytes()==source.read_bytes()
    assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(source.read_bytes()).digest()
    target.unlink()
    original=runtime._validated_bundle
    monkeypatch.setattr(runtime,'_validated_bundle',lambda path:original(path)+(b'\n' if Path(path)==target else b''))
    with pytest.raises(runtime.RuntimeConfigurationError,match='integridad'):runtime._ascii_bundle(source)


def test_short_alias_avoids_copy_only_if_content_is_identical(tmp_path,monkeypatch):
    source=tmp_path/'José.pem';alias=tmp_path/'JOSE~1.pem'
    data=Path(certifi.where()).read_bytes();source.write_bytes(data);alias.write_bytes(data)
    monkeypatch.setattr(runtime,'_short_path',lambda path:alias)
    monkeypatch.setattr(runtime,'_private_ascii_directory',lambda:pytest.fail('No se debe copiar si el alias válido existe'))
    assert runtime._ascii_bundle(source)==str(alias)


def test_explicit_ca_settings_preserved_and_failure_is_atomic(tmp_path,monkeypatch):
    paths={k:str(tmp_path/(k+'.pem')) for k in runtime.CA_VARIABLES}
    for path in paths.values():Path(path).write_bytes(Path(certifi.where()).read_bytes())
    original=dict(paths);runtime._configure_windows_ca(paths)
    assert paths==original
    paths['SSL_CERT_FILE']=str(tmp_path/'missing.pem');before=dict(paths)
    with pytest.raises(runtime.RuntimeConfigurationError,match='CA_LOCAL'):runtime._configure_windows_ca(paths)
    assert paths==before


def test_default_ca_comes_from_certifi_and_invalid_pem_fails(tmp_path,monkeypatch):
    env={};runtime._configure_windows_ca(env)
    assert set(env)==set(runtime.CA_VARIABLES)
    assert all(Path(p).read_bytes()==Path(certifi.where()).read_bytes() for p in env.values())
    invalid=tmp_path/'invalid.pem';invalid.write_bytes(b'not a CA')
    with pytest.raises(runtime.RuntimeConfigurationError,match='CA_LOCAL'):runtime._validated_bundle(invalid)


def test_ca_permissions_failure_is_clear_and_does_not_change_environment(monkeypatch):
    env={}
    def denied(path):raise PermissionError('denied')
    monkeypatch.setattr(runtime,'_ascii_bundle',denied)
    with pytest.raises(runtime.RuntimeConfigurationError,match='permisos seguros'):runtime._configure_windows_ca(env)
    assert env=={}


@pytest.mark.skipif(sys.platform!='win32',reason='DACL nativa de Windows: se ejecuta en GitHub Actions Windows')
def test_windows_unicode_ca_native_private_acl(tmp_path,monkeypatch):
    source=tmp_path/'Álvaro 日本'/'ca.pem';source.parent.mkdir();source.write_bytes(Path(certifi.where()).read_bytes())
    monkeypatch.setattr(runtime,'_short_path',lambda path:None)  # Fuerza fallback sin depender de 8.3.
    target=Path(runtime._ascii_bundle(source))
    assert str(target).isascii() and target.read_bytes()==source.read_bytes()
    from ctypes import wintypes as w
    adv=ctypes.WinDLL('advapi32',use_last_error=True);kernel=ctypes.WinDLL('kernel32')
    descriptor=ctypes.c_void_p();text=w.LPWSTR()
    adv.GetNamedSecurityInfoW.argtypes=[w.LPWSTR,w.DWORD,w.DWORD,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes=[ctypes.c_void_p,w.DWORD,w.DWORD,ctypes.POINTER(w.LPWSTR),ctypes.c_void_p]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    try:
        assert adv.GetNamedSecurityInfoW(str(target.parent),1,4,None,None,None,None,ctypes.byref(descriptor))==0
        assert adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor,1,4,ctypes.byref(text),None)
        dacl=text.value
        assert dacl.startswith('D:P') and dacl.count('(A;')==2
        assert ';;;SY)' in dacl and ';;;WD)' not in dacl and ';;;BU)' not in dacl and ';;;AU)' not in dacl
    finally:
        if text:kernel.LocalFree(ctypes.cast(text,ctypes.c_void_p))
        if descriptor:kernel.LocalFree(descriptor)


@pytest.fixture
def https_local():
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Length','11');self.end_headers();self.wfile.write(b'{"ok":true}')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(TLS/'localhost.pem',TLS/'localhost.key')
    context.set_alpn_protocols(['http/1.1'])
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'https://127.0.0.1:{server.server_port}/'
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_real_curl_and_requests_https_from_unicode_ca_keep_verification(https_local,tmp_path,monkeypatch):
    from curl_cffi import requests as curl
    source=tmp_path/'Álvaro 日本.pem';source.write_bytes((TLS/'localhost.pem').read_bytes())
    for key in runtime.CA_VARIABLES:monkeypatch.setenv(key,str(source))
    monkeypatch.setenv('NO_PROXY','127.0.0.1,localhost')
    monkeypatch.setenv('no_proxy','127.0.0.1,localhost')
    if sys.platform!='win32':
        private=tmp_path/'private';private.mkdir()
        monkeypatch.setattr(runtime,'_short_path',lambda path:None)
        monkeypatch.setattr(runtime,'_private_ascii_directory',lambda:private)
    runtime._configure_windows_ca(os.environ)
    with curl.Session() as session:
        assert session.get(https_local,timeout=5).json()=={'ok':True}
        with pytest.raises(curl.exceptions.SSLError):session.get(https_local,verify=certifi.where(),timeout=5)
    assert requests.get(https_local,timeout=5).json()=={'ok':True}


@pytest.mark.parametrize('error,provider,expected',[
    (requests.exceptions.SSLError('bad certificate'),'Yahoo','[SSL]'),
    (requests.exceptions.ConnectionError('offline'),'Yahoo','[RED_CONEXION]'),
    (requests.exceptions.Timeout('timeout'),'SEC','[RED_TIMEOUT]'),
    (ValueError('invalid JSON'),'SEC','[DATOS_INCOMPLETOS]'),
    (type('YFRateLimitError',(Exception,),{})('rate limited'),'Yahoo','[LIMITE_YAHOO]'),
])
def test_transport_diagnostics_separate_failure_types(error,provider,expected):
    assert expected in runtime.network_diagnostic(error,provider)


@pytest.mark.parametrize('status,provider,expected',[(403,'SEC','SEC_HTTP_403'),(429,'Yahoo','LIMITE_YAHOO'),(403,'Yahoo','HTTP_403')])
def test_http_diagnostics_are_not_ssl(status,provider,expected):
    response=requests.Response();response.status_code=status
    error=requests.HTTPError('denied',response=response)
    assert expected in runtime.network_diagnostic(error,provider)
    assert '[SSL]' not in runtime.network_diagnostic(error,provider)


def test_curl_local_ca_error_is_not_a_rate_limit():
    error=RuntimeError('curl: (77) error adding trust anchors from locations')
    assert '[CA_LOCAL]' in runtime.network_diagnostic(error,'Yahoo')


@pytest.mark.parametrize('payload',[None,[], 'incomplete'])
def test_sec_incomplete_response_fails_explicitly(payload,monkeypatch):
    import sec_historical
    monkeypatch.setattr(sec_historical.requests,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload))
    with pytest.warns(UserWarning,match='DATOS_INCOMPLETOS'):
        with pytest.raises(ValueError):sec_historical._get_json('https://data.sec.gov/test','test')


def test_sec_http403_keeps_error_type_and_distinct_diagnostic(monkeypatch):
    import sec_historical
    response=requests.Response();response.status_code=403
    def fail(*a,**k):raise requests.HTTPError('denied',response=response)
    monkeypatch.setattr(sec_historical.requests,'get',fail)
    with pytest.warns(UserWarning,match='SEC_HTTP_403'):
        with pytest.raises(requests.HTTPError):sec_historical._get_json('https://data.sec.gov/test','test')


def test_dashboard_unicode_capture_preserves_manual_pe_and_financial_warnings(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    from tests.test_v7_integrada import archived
    from estado_dashboard import per_settings
    from copy import deepcopy
    p=deepcopy(archived('AMZN'))
    settings=per_settings({'scenarios':{'Base':{'growth':.10}}},'Manual',20.,.2,.2,'Sensibilidad — acción; no recomendación')
    p['evidence']['stock_model']['settings']=settings
    path=tmp_path/'Álvaro 日本.json';path.write_text(json.dumps(p,ensure_ascii=False),encoding='utf-8')
    monkeypatch.setenv('VALUACION_DASHBOARD_SNAPSHOT',str(path))
    app=AppTest.from_file(ROOT/'dashboard_app.py').run(timeout=40)
    assert not app.exception and app.metric[1].value!='—'
    next(b for b in app.button if b.label=='Recalcular escenarios').click().run(timeout=40)
    stored=json.loads(app.session_state['settings'])
    assert stored['scenarios']['Base']['pe']==20. and stored['scenarios']['Base']['growth']==.10
    assert not app.exception


def test_real_dashboard_start_from_unicode_directory(tmp_path):
    from iniciar_dashboard import start_dashboard
    folder=tmp_path/'Álvaro 日本 & !';folder.mkdir()
    (folder/'dashboard_app.py').write_text('import streamlit as st\nst.write("V7 − á 日本")\n',encoding='utf-8')
    state=start_dashboard(Path(sys.executable),folder,open_browser=False,wait_seconds=20)
    try:
        saved=json.loads((folder/'.dashboard_servidor.json').read_text(encoding='utf-8'))
        assert saved==state and 'Álvaro 日本' in saved['AppFile']
    finally:
        os.kill(state['PID'],signal.SIGTERM)


def test_launcher_completes_dependencies_without_patching_code(tmp_path,monkeypatch):
    import iniciar_dashboard as launch
    folder=tmp_path/'.venv';python=folder/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    python.parent.mkdir(parents=True);python.touch()
    calls=[];failed=False
    def checked(args,*a,**k):
        nonlocal failed
        calls.append(args)
        if launch.CHECK in args and not failed:
            failed=True;raise RuntimeError('missing dependency')
    monkeypatch.setattr(launch,'checked',checked)
    assert launch.prepare_environment(tmp_path)==python
    assert any('install' in args and 'requirements.lock' in args for args in calls)
    assert all('git' not in args for args in calls)


def test_incomplete_yahoo_has_no_fabricated_targets(tmp_path):
    from ejecutar_analisis import save_unavailable
    import pandas as pd
    assert save_unavailable('MISSING',tmp_path,pd.Timestamp('2026-11-13',tz='UTC'))==2
    output=json.loads((tmp_path/'MISSING_resumen.json').read_text(encoding='utf-8'))
    assert output['auditoria']['objetivos_principales_disponibles']==0
    assert not output['auditoria']['publicable']
