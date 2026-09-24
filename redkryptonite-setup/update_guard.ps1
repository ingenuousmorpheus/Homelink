# =====================================================================
#  HomeLink House Guard - updater for any guard laptop
#  Stops the running guard, installs the new multi-camera server,
#  and restarts it. Run on the laptop:
#    irm http://100.107.136.88:8080/guard-update/update_guard.ps1 | iex
# =====================================================================

$ErrorActionPreference = 'Stop'
$PackageBase = 'http://100.107.136.88:8080/guard-update'
$InstallDir  = 'C:\HomeLink\backend'
$TaskName    = 'HomeLinkGuard'
$StartBat    = Join-Path $InstallDir 'start_guard.bat'

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights needed - a popup will appear. Click YES." -ForegroundColor Yellow
    $tmp = Join-Path $env:TEMP 'homelink-update.ps1'
    if ($PSCommandPath) { Copy-Item $PSCommandPath $tmp -Force }
    else { Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/update_guard.ps1" -OutFile $tmp }
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$tmp`""
    return
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

Write-Host "=== Stopping the running guard ===" -ForegroundColor Cyan
$conn = Get-NetTCPConnection -LocalPort 7171 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Stop-Process -Id $conn.OwningProcess -Force
    Start-Sleep -Seconds 1
    Write-Host "  [OK] Old guard stopped" -ForegroundColor Green
} else {
    Write-Host "  [!] Guard was not running" -ForegroundColor Yellow
}

Write-Host "=== Installing multi-camera server ===" -ForegroundColor Cyan
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/camera_server.py" -OutFile (Join-Path $InstallDir 'camera_server.py')
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/camera_requirements.txt" -OutFile (Join-Path $InstallDir 'camera_requirements.txt')
Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/start_guard.bat" -OutFile $StartBat
Write-Host "  [OK] camera_server.py updated" -ForegroundColor Green

Write-Host "=== Installing audio support (live microphone) ===" -ForegroundColor Cyan
& python -m pip install -r (Join-Path $InstallDir 'camera_requirements.txt') --quiet --disable-pip-version-check
Write-Host "  [OK] sounddevice + pygrabber installed" -ForegroundColor Green

Write-Host "=== Opening firewall for HomeLink Guard ===" -ForegroundColor Cyan
netsh advfirewall firewall delete rule name="HomeLink Guard 7171" | Out-Null
netsh advfirewall firewall add rule name="HomeLink Guard 7171" dir=in action=allow protocol=TCP localport=7171 profile=any | Out-Null
Write-Host "  [OK] TCP 7171 allowed" -ForegroundColor Green

Write-Host "=== Installing always-on startup task ===" -ForegroundColor Cyan
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $StartBat -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "  [OK] $TaskName will start at sign-in with highest privileges" -ForegroundColor Green

Write-Host "=== Restarting the guard ===" -ForegroundColor Cyan
Start-Process $StartBat -WorkingDirectory $InstallDir
Write-Host "  [OK] Guard restarting - it now auto-detects up to 10 cameras" -ForegroundColor Green
Start-Sleep -Seconds 8

$probe = $null
try {
    $probe = Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:7171/?key=home-link-secret' -TimeoutSec 10
} catch {
    Write-Host "  [!] Local status check did not answer yet: $($_.Exception.Message)" -ForegroundColor Yellow
}
if ($probe) {
    Write-Host "  [OK] Guard answered locally as $($probe.node_id) with $($probe.cameras.Count) camera(s)" -ForegroundColor Green
}
Write-Host ""
Write-Host "Done! Give it ~30 seconds, then check the SENTINEL tab in the app." -ForegroundColor Green
Write-Host "Every webcam on this machine should appear on the CCTV grid." -ForegroundColor Green
Write-Host ""
Write-Host "New in this build:" -ForegroundColor Cyan
Write-Host "  * Motion stills and manual CAPTURE shots save to X:\Camera Roll."
Write-Host "  * WAKE in the app now RE-DETECTS the cameras, so moving a webcam"
Write-Host "    to a different USB port no longer needs anyone to touch this PC."
Write-Host "  * A wedged audio driver can no longer stop the cameras from starting."
