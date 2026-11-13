# Compatibilidad con accesos directos existentes; hay un unico flujo de arranque.
& (Join-Path $PSScriptRoot 'iniciar_dashboard.bat')
exit $LASTEXITCODE
