@echo off
setlocal DisableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
pushd "%~dp0" || (echo ERROR: no se puede abrir la carpeta del proyecto. & pause & exit /b 1)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32" >nul 2>&1
    if not errorlevel 1 (
        ".venv\Scripts\python.exe" -X utf8 iniciar_dashboard.py
        goto resultado
    )
)
py -3.12 -c "import sys; assert sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -X utf8 iniciar_dashboard.py
    goto resultado
)
python -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 (
    python -X utf8 iniciar_dashboard.py
    goto resultado
)
echo ERROR: no se encuentra Python 3.12 de 64 bits. Instalalo desde python.org y vuelve a abrir este archivo.
set "RESULTADO=1"
goto fin
:resultado
set "RESULTADO=%ERRORLEVEL%"
:fin
popd
if not "%RESULTADO%"=="0" if not "%CI%"=="true" pause
exit /b %RESULTADO%
