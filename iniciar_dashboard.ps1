# Lanzador portable para Windows PowerShell 5.1 y posteriores.
# Todas las rutas derivan de la ubicacion del propio .ps1.
$ErrorActionPreference = 'Stop'
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppFile = Join-Path $AppDir 'dashboard_app.py'
$EngineFile = Join-Path $AppDir 'valoracion_engine.py'
$SecFile = Join-Path $AppDir 'sec_historical.py'
$ModelFile = Join-Path $AppDir 'modelo_fundamental.py'
$PeerFile = Join-Path $AppDir 'comparables_inteligentes.py'
$PeerConfig = Join-Path $AppDir 'comparables_config.json'
$Requirements = Join-Path $AppDir 'requirements.lock'
$StateFile = Join-Path $AppDir '.dashboard_servidor.json'
$LogDir = Join-Path $AppDir 'logs'

function Get-ExistingExe([string]$directory, [string]$relative) {
    if ([string]::IsNullOrWhiteSpace($directory)) { return $null }
    $candidate = Join-Path $directory $relative
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Find-Python {
    $candidates = New-Object System.Collections.ArrayList
    $locations = @(
        [pscustomobject]@{ Dir = $AppDir; Relative = '.venv\Scripts\python.exe' },
        [pscustomobject]@{ Dir = $AppDir; Relative = '.venv\Scripts\python.exe' },
        [pscustomobject]@{ Dir = $env:VIRTUAL_ENV; Relative = 'Scripts\python.exe' },
        [pscustomobject]@{ Dir = $env:CONDA_PREFIX; Relative = 'python.exe' },
        [pscustomobject]@{ Dir = $env:ProgramData; Relative = 'anaconda3\python.exe' },
        [pscustomobject]@{ Dir = $env:ProgramData; Relative = 'Anaconda3\python.exe' },
        [pscustomobject]@{ Dir = $env:USERPROFILE; Relative = 'anaconda3\python.exe' },
        [pscustomobject]@{ Dir = $env:USERPROFILE; Relative = 'miniconda3\python.exe' },
        [pscustomobject]@{ Dir = $env:LOCALAPPDATA; Relative = 'anaconda3\python.exe' },
        [pscustomobject]@{ Dir = $env:LOCALAPPDATA; Relative = 'Programs\Python\Python313\python.exe' },
        [pscustomobject]@{ Dir = $env:LOCALAPPDATA; Relative = 'Programs\Python\Python312\python.exe' },
        [pscustomobject]@{ Dir = $env:LOCALAPPDATA; Relative = 'Programs\Python\Python311\python.exe' }
    )
    foreach ($location in $locations) {
        $exe = Get-ExistingExe $location.Dir $location.Relative
        if ($exe -and -not ($candidates | Where-Object { $_.Exe -eq $exe })) {
            [void]$candidates.Add([pscustomobject]@{ Exe = $exe; Prefix = @() })
        }
    }
    foreach ($name in @('python.exe','python3.exe','py.exe')) {
        foreach ($cmd in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            $exe = $cmd.Source
            if (-not $exe -or $exe -match 'WindowsApps') { continue }
            if (-not ($candidates | Where-Object { $_.Exe -eq $exe })) {
                $prefix = @()
                if ($name -eq 'py.exe') { $prefix = @('-3') }
                [void]$candidates.Add([pscustomobject]@{ Exe = $exe; Prefix = $prefix })
            }
        }
    }
    $firstWorking = $null
    foreach ($candidate in $candidates) {
        try {
            $candidateArgs = @($candidate.Prefix)
            & $candidate.Exe @candidateArgs -c 'import sys; assert sys.version_info >= (3, 12)' 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) { continue }
            if ($null -eq $firstWorking) { $firstWorking = $candidate }
            & $candidate.Exe @candidateArgs -c 'import streamlit, pandas, numpy, yfinance, openpyxl, requests, bs4; from streamlit.proto import RootContainer_pb2' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch { continue }
    }
    return $firstWorking
}

function Test-Http([int]$port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_stcore/health" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch { return $false }
}

function Find-FreePort {
    foreach ($port in 8501..8540) {
        $listener = $null
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $listener.Start()
            return $port
        } catch {} finally {
            if ($null -ne $listener) { $listener.Stop() }
        }
    }
    throw 'No hay puertos disponibles entre 8501 y 8540.'
}

function Get-RunningDashboard {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    try {
        $saved = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        if ($saved.AppFile -ne $AppFile) { return $null }
        $proc = Get-Process -Id ([int]$saved.PID) -ErrorAction SilentlyContinue
        if ($null -eq $proc) { return $null }
        if (Test-Http ([int]$saved.Port)) { return $saved }
    } catch {}
    return $null
}

function Open-Browser([int]$port) {
    $url = "http://127.0.0.1:$port"
    $locations = @(
        [pscustomobject]@{ Dir = $AppDir; Relative = '.venv\Scripts\python.exe' },
        (Get-ExistingExe $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Get-ExistingExe ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Google\Chrome\Application\chrome.exe'),
        (Get-ExistingExe $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    )
    $chrome = $locations | Where-Object { $_ } | Select-Object -First 1
    if ($chrome) {
        Start-Process -FilePath $chrome -ArgumentList "--app=$url"
    } else {
        Start-Process $url
    }
}

try {
    foreach ($file in @($AppFile, $EngineFile, $SecFile, $ModelFile, $PeerFile, $PeerConfig, $Requirements)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Falta el archivo: $file. Extrae el ZIP entero, no solo los .bat."
        }
    }

    $existing = Get-RunningDashboard
    if ($existing) {
        Write-Host "Abriendo el dashboard ya iniciado (puerto $($existing.Port))..." -ForegroundColor Green
        Open-Browser ([int]$existing.Port)
        exit 0
    }

    Write-Host 'Dashboard de valoracion SEC + Yahoo' -ForegroundColor Cyan
    Write-Host "Carpeta: $AppDir"
    $python = Find-Python
    if ($null -eq $python) {
        throw 'No se encontro Python 3.12+ instalado. Instala Python o Anaconda y vuelve a abrir iniciar_dashboard.bat.'
    }
    Write-Host "Python: $($python.Exe)"

    # Verifica TODAS las bibliotecas necesarias, no solamente Streamlit.
    $pythonArgs = @($python.Prefix)
    & $python.Exe @pythonArgs -c 'import streamlit, pandas, numpy, yfinance, openpyxl, requests, bs4; from streamlit.proto import RootContainer_pb2' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Instalando bibliotecas ausentes (requiere Internet)...' -ForegroundColor Yellow
        & $python.Exe @pythonArgs -m pip install -r $Requirements
        if ($LASTEXITCODE -ne 0) {
            throw 'Error instalando paquetes. Abre Anaconda Prompt y ejecuta: python -m pip install -r "requirements.lock" dentro de la carpeta del dashboard.'
        }
    }
    if (-not (Test-Path -LiteralPath $LogDir)) {
        [void](New-Item -ItemType Directory -Path $LogDir -Force)
    }
    $port = Find-FreePort
    $stdout = Join-Path $LogDir 'servidor_salida.log'
    $stderr = Join-Path $LogDir 'servidor_errores.log'
    $serverArguments = @($python.Prefix) + @(
        '-m','streamlit','run',('"' + $AppFile + '"'),
        '--server.address=127.0.0.1','--server.headless=true',"--server.port=$port",
        '--browser.gatherUsageStats=false'
    )
    $server = Start-Process -FilePath $python.Exe -ArgumentList $serverArguments `
        -WorkingDirectory $AppDir -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru

    $ready = $false
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Http $port) { $ready = $true; break }
        $server.Refresh()
        if ($server.HasExited) { break }
    }
    if (-not $ready) {
        $details = ''
        if (Test-Path -LiteralPath $stderr) { $details = (Get-Content -LiteralPath $stderr -Tail 25 -ErrorAction SilentlyContinue) -join "`n" }
        throw "Streamlit no pudo iniciarse. Revisa $stderr`n$details"
    }

    # Guarda el proceso y puerto para poder reutilizarlo y cerrarlo.
    [pscustomobject]@{ PID = $server.Id; Port = $port; AppFile = $AppFile } |
        ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
    Write-Host "Dashboard iniciado: http://127.0.0.1:$port" -ForegroundColor Green
    Write-Host "Registros de errores: $stderr"
    Write-Host 'Para cerrarlo, utiliza cerrar_dashboard.bat.'
    Open-Browser $port
} catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Host "Directorio utilizado: $AppDir" -ForegroundColor Yellow
    Read-Host 'Pulsa Intro para cerrar y copiar el mensaje si necesitas ayuda'
    exit 1
}
