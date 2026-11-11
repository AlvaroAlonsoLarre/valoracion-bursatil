@echo off
setlocal
pushd "%~dp0" || (echo No se encuentra la carpeta del dashboard. & pause & exit /b 1)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0cerrar_dashboard.ps1"
set "RESULTADO=%ERRORLEVEL%"
popd
if not "%RESULTADO%"=="0" pause
exit /b %RESULTADO%
