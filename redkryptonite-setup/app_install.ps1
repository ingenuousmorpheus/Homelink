# =====================================================================
#  HomeLink App Server - installer (run on the machine that should HOST
#  the HomeLink web app, e.g. LenovoMonitor).
#
#  On that machine, in any PowerShell window:
#    irm http://100.107.136.88:8080/guard-update/app_install.ps1 | iex
#
#  Installs the app to C:\HomeLink\app, serves it on port 8080, and
#  auto-starts it at every logon so HomeLink is always reachable.
# =====================================================================

$ErrorActionPreference = 'Stop'
$PackageBase = 'http://100.107.136.88:8080/guard-update'
$InstallDir  = 'C:\HomeLink\app'
$Port        = 8080

function Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!] $m" -ForegroundColor Yellow }

# Self-elevate: needed for the Startup shortcut + firewall rule.
$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights needed - a popup will appear. Click YES." -ForegroundColor Yellow
    $tmp = Join-Path $env:TEMP 'homelink-app-install.ps1'
    if ($PSCommandPath) { Copy-Item $PSCommandPath $tmp -Force }
    else { Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/app_install.ps1" -OutFile $tmp }
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$tmp`""
    Write-Host "Continuing in the new (elevated) window..."
    return
}

Step "1/6 Checking Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Warn "Python not found - installing"
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
Ok "Python: $(& python --version)"

Step "2/6 Stopping any app server already on port $Port"
$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Start-Sleep -Seconds 1; Ok "Old server stopped" }
else { Ok "Port $Port free" }

Step "3/6 Downloading the HomeLink app"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$zip = Join-Path $env:TEMP 'homelink_app.zip'
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/homelink_app.zip" -OutFile $zip
# clear old build so stale hashed asset files don't accumulate
if (Test-Path (Join-Path $InstallDir 'dist')) { Remove-Item (Join-Path $InstallDir 'dist') -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $InstallDir -Force
Remove-Item $zip -Force
Ok "App installed to $InstallDir"

Step "4/6 Creating the launcher"
$bat = Join-Path $InstallDir 'start_homelink_app.bat'
@"
@echo off
title HomeLink App Server
cd /d "%~dp0"
python serve_app.py
pause
"@ | Set-Content -Path $bat -Encoding ascii
Ok "Launcher written"

Step "5/6 Firewall + auto-start on boot"
try {
    if (-not (Get-NetFirewallRule -DisplayName 'HomeLink App 8080' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'HomeLink App 8080' -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $Port -Profile Any | Out-Null
    }
    Ok "Firewall allows port $Port"
} catch { Warn "Could not add firewall rule: $($_.Exception.Message)" }

$startup = [Environment]::GetFolderPath('Startup')
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut((Join-Path $startup 'HomeLink App.lnk'))
$sc.TargetPath = $bat
$sc.WorkingDirectory = $InstallDir
$sc.WindowStyle = 7          # start minimized
$sc.Save()
Ok "Auto-starts at every logon"

Step "6/6 Starting the server"
Start-Process -FilePath $bat -WorkingDirectory $InstallDir -WindowStyle Minimized
Start-Sleep -Seconds 4
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$Port/" -TimeoutSec 8
    Ok "Serving (HTTP $($r.StatusCode))"
} catch { Warn "Not answering yet - give it a few seconds" }

$tsExe = "$env:ProgramFiles\Tailscale\tailscale.exe"
$tsIp = if (Test-Path $tsExe) { (& $tsExe ip -4 2>$null | Select-Object -First 1) } else { $null }

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  HOMELINK IS NOW HOSTED ON THIS MACHINE" -ForegroundColor Green
if ($tsIp) { Write-Host "  Open from any device:  http://${tsIp}:$Port" -ForegroundColor Cyan }
Write-Host "  It restarts automatically whenever this PC boots."
Write-Host "==============================================" -ForegroundColor Green
