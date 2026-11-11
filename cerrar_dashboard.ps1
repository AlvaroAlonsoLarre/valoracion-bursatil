$ErrorActionPreference = 'Stop'
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateFile = Join-Path $AppDir '.dashboard_servidor.json'
try {
    if (-not (Test-Path -LiteralPath $StateFile)) {
        Write-Host 'No hay un servidor registrado en esta carpeta.'
        exit 0
    }
    $saved = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
    $expectedAppFile = Join-Path $AppDir 'dashboard_app.py'
    if ($saved.AppFile -ne $expectedAppFile) {
        throw 'Los datos del servidor no corresponden con esta carpeta.'
    }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$saved.PID)" -ErrorAction SilentlyContinue
    if ($null -ne $proc) {
        $cmd = [string]$proc.CommandLine
        if ($cmd -notlike '*streamlit*' -or $cmd -notlike '*dashboard_app.py*') {
            throw 'El identificador pertenece a otro programa. No se cerrara ningun proceso.'
        }
        Stop-Process -Id ([int]$saved.PID) -Force -ErrorAction Stop
        Write-Host 'Dashboard cerrado.' -ForegroundColor Green
    } else {
        Write-Host 'El servidor ya estaba cerrado.'
    }
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Pulsa Intro para cerrar'
    exit 1
}
