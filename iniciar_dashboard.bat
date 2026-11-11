@echo off
setlocal
REM %~dp0 = carpeta de este BAT, aunque se ejecute desde otra ubicacion.
pushd "%~dp0" || (echo No se puede acceder a la carpeta del dashboard. & pause & exit /b 1)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_dashboard.ps1"
set "RESULTADO=%ERRORLEVEL%"
popd
if not "%RESULTADO%"=="0" (
    echo.
    echo Error al iniciar el dashboard. Revisa el mensaje anterior y la carpeta logs.
    pause
)
exit /b %RESULTADO%
