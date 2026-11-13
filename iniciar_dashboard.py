"""Arranque desde el ZIP/repositorio: prepara dependencias, nunca parchea código."""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
import venv
import webbrowser
from entorno_ejecucion import configure_utf8, child_environment

ROOT = Path(__file__).resolve().parent
CHECK = '''
from importlib.metadata import version
from pathlib import Path
import streamlit, pandas, numpy, yfinance, openpyxl, requests, bs4, curl_cffi
from streamlit.proto import RootContainer_pb2
for line in Path('requirements.lock').read_text(encoding='utf-8').splitlines():
    if line.strip() and not line.startswith('#'):
        name, expected = line.split('==')
        assert version(name) == expected, name + ': versión distinta de requirements.lock'
'''


def checked(args, root=ROOT, timeout=900):
    proc = subprocess.run(args, cwd=root, env=child_environment(), capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout)[-3000:])
    return proc


def prepare_environment(root=ROOT):
    if sys.version_info[:2] != (3, 12) or sys.maxsize <= 2**32:
        raise RuntimeError('Instala Python 3.12 de 64 bits y abre iniciar_dashboard.bat de nuevo')
    folder = root / '.venv'
    python = folder / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not folder.exists():
        print('Creando el entorno .venv (sin modificar el proyecto)...')
        venv.EnvBuilder(with_pip=True).create(folder)
    if not python.is_file():
        raise RuntimeError('La carpeta .venv está incompleta. Renómbrala para conservarla y vuelve a iniciar')
    try:
        checked([str(python), '-X', 'utf8', '-c', 'import sys; assert sys.version_info[:2] == (3,12)'], root)
    except RuntimeError as exc:
        raise RuntimeError('.venv no usa Python 3.12. Renómbrala para conservarla y vuelve a iniciar') from exc
    try:
        checked([str(python), '-X', 'utf8', '-c', CHECK], root)
        checked([str(python), '-m', 'pip', 'check'], root)
    except RuntimeError:
        print('Instalando/completando las dependencias fijadas; requiere Internet...')
        checked([str(python), '-m', 'pip', 'install', '-r', 'requirements.lock'], root)
        checked([str(python), '-X', 'utf8', '-c', CHECK], root)
        checked([str(python), '-m', 'pip', 'check'], root)
    checked([str(python), '-X', 'utf8', '-c', 'from entorno_ejecucion import configure_runtime; configure_runtime()'], root)
    return python


def free_port():
    for port in range(8501, 8541):
        with socket.socket() as listener:
            try:listener.bind(('127.0.0.1', port));return port
            except OSError:continue
    raise RuntimeError('No hay puertos libres entre 8501 y 8540. Cierra el servidor anterior')


def start_dashboard(python, root=ROOT, open_browser=True, wait_seconds=45):
    logs = root / 'logs';logs.mkdir(exist_ok=True)
    port = free_port();app = root / 'dashboard_app.py'
    command = [str(python), '-X', 'utf8', '-m', 'streamlit', 'run', str(app),
               '--server.address=127.0.0.1', '--server.headless=true', f'--server.port={port}',
               '--browser.gatherUsageStats=false']
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    with (logs / 'servidor_salida.log').open('w', encoding='utf-8') as out, (logs / 'servidor_errores.log').open('w', encoding='utf-8') as err:
        proc = subprocess.Popen(command, cwd=root, env=child_environment(), stdout=out, stderr=err, **options)
    opener = build_opener(ProxyHandler({}));deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:break
        try:
            with opener.open(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
                if response.status == 200:
                    state = {'PID': proc.pid, 'Port': port, 'AppFile': str(app)}
                    (root / '.dashboard_servidor.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
                    url = f'http://127.0.0.1:{port}'
                    print('Dashboard iniciado: ' + url)
                    if open_browser:
                        try:webbrowser.open(url)
                        except OSError:print('Abre la URL anterior en el navegador')
                    return state
        except OSError:pass
        time.sleep(.25)
    if proc.poll() is None:
        proc.terminate();proc.wait(timeout=10)
    detail = (logs / 'servidor_errores.log').read_text(encoding='utf-8', errors='replace')[-3000:]
    raise RuntimeError('Streamlit no pudo iniciarse. Revisa logs/servidor_errores.log\n' + detail)


def main():
    configure_utf8()
    try:
        print('V7 integrada — UTF-8 / HTTPS verificado')
        start_dashboard(prepare_environment(),open_browser=os.environ.get('VALUACION_NO_BROWSER') != '1')
        print('Para cerrar el servidor usa cerrar_dashboard.bat')
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        print('Extrae el ZIP completo en una ruta corta, por ejemplo C:\\Bolsa. Se admiten nombres Unicode.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
