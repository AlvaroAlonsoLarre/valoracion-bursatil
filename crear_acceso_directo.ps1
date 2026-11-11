$ErrorActionPreference = 'Stop'
$AppDir = $PSScriptRoot
$Launcher = Join-Path $AppDir 'iniciar_dashboard.ps1'
if (-not (Test-Path $Launcher)) {
    Write-Host 'No se encuentra iniciar_dashboard.ps1 en esta carpeta.' -ForegroundColor Red
    Read-Host 'Pulsa Intro para cerrar'
    exit 1
}

$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop 'Valoracion Yahoo Finance.lnk'
$PowerShellExe = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$ChromeCandidates = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$IconExe = $PowerShellExe
foreach ($candidate in $ChromeCandidates) {
    if ($candidate -and (Test-Path $candidate)) { $IconExe = $candidate; break }
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PowerShellExe
$Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Launcher + '"'
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.IconLocation = $IconExe + ',0'
$Shortcut.Description = 'Inicia el panel local de valoracion bursatil de Yahoo Finance'
$Shortcut.Save()

Write-Host ''
Write-Host 'Acceso directo creado en el Escritorio:' -ForegroundColor Green
Write-Host $ShortcutPath
Write-Host ''
Write-Host 'Para anadirlo a la barra de tareas:'
Write-Host '1. Haz clic derecho en el acceso directo del Escritorio.'
Write-Host '2. En Windows 11, selecciona Mostrar mas opciones si aparece.'
Write-Host '3. Pulsa Anclar a la barra de tareas.'
Write-Host 'Si no aparece esa opcion, abre el acceso directo una vez y pulsa clic derecho sobre su icono en la barra de tareas.'
Read-Host 'Pulsa Intro para cerrar'
