# =====================================================================
#  LANA OS Link - RedKryptonite remote arm installer
#  Run on RedKryptonite:
#    irm http://100.107.136.88:8080/guard-update/install_lana_arm.ps1 | iex
# =====================================================================

$ErrorActionPreference = 'Stop'
$PackageBase = 'http://100.107.136.88:8080/guard-update'
$InstallDir = 'C:\LanaArm'
$TaskName = 'LanaArm'
$Port = 7060

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Administrator rights needed - a popup will appear. Click YES.' -ForegroundColor Yellow
    $tmp = Join-Path $env:TEMP 'install-lana-arm.ps1'
    if ($PSCommandPath) { Copy-Item $PSCommandPath $tmp -Force }
    else { Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/install_lana_arm.ps1" -OutFile $tmp }
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$tmp`""
    return
}

Write-Host '=== Installing LANA OS Link remote arm ===' -ForegroundColor Cyan
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/lana_agent.py" -OutFile (Join-Path $InstallDir 'lana_agent.py')
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/lana_netscan.py" -OutFile (Join-Path $InstallDir 'lana_netscan.py')
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/redkryptonite_lana_token.txt" -OutFile (Join-Path $InstallDir 'agent_token.txt')

$startBat = Join-Path $InstallDir 'start_lana_arm.bat'
$bat = @'
@echo off
cd /d "%~dp0"
set /p LANA_AGENT_TOKEN=<"%~dp0agent_token.txt"
set "LANA_AGENT_PORT=7060"
set "LANA_AGENT_ALLOW_SHELL=1"
set "LANA_AGENT_CORS_ORIGINS=*"
set "PYTHONUTF8=1"
set "LOG=%~dp0agent.log"

where python >nul 2>nul
if errorlevel 1 (
    echo Python is not installed or not on PATH. >> "%LOG%"
    exit /b 1
)

:run
echo [%date% %time%] Starting LANA remote arm... >> "%LOG%"
python lana_agent.py >> "%LOG%" 2>&1
echo [%date% %time%] lana_agent.py exited with code %errorlevel% >> "%LOG%"
timeout /t 5 /nobreak >nul
goto run
'@
Set-Content -LiteralPath $startBat -Value $bat -Encoding ASCII

Write-Host '=== Installing Python dependencies ===' -ForegroundColor Cyan
& python -m pip install flask flask-cors pyautogui mss opencv-python sounddevice numpy pillow pyperclip --quiet --disable-pip-version-check
Write-Host '  [OK] dependencies installed' -ForegroundColor Green

Write-Host '=== Opening firewall for LANA OS Link ===' -ForegroundColor Cyan
netsh advfirewall firewall delete rule name='LanaArm-7060' | Out-Null
netsh advfirewall firewall add rule name='LanaArm-7060' dir=in action=allow protocol=TCP localport=$Port remoteip=192.168.1.0/24,100.64.0.0/10 profile=any | Out-Null
Write-Host '  [OK] TCP 7060 allowed from LAN and Tailscale' -ForegroundColor Green

Write-Host '=== Installing startup task ===' -ForegroundColor Cyan
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $startBat -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "  [OK] $TaskName will start at sign-in with highest privileges" -ForegroundColor Green

Write-Host '=== Starting LANA OS Link ===' -ForegroundColor Cyan
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
Start-Process $startBat -WorkingDirectory $InstallDir
Start-Sleep -Seconds 5

try {
    $token = (Get-Content -LiteralPath (Join-Path $InstallDir 'agent_token.txt') -Raw).Trim()
    $status = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$Port/status" -Headers @{ 'X-Lana-Token' = $token } -TimeoutSec 10
    Write-Host "  [OK] LANA OS Link answered as $($status.host), shell_enabled=$($status.shell_enabled)" -ForegroundColor Green
} catch {
    Write-Host "  [!] LANA OS Link did not answer yet: $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Done. Codex should now be able to reach RedKryptonite on port 7060.' -ForegroundColor Green
