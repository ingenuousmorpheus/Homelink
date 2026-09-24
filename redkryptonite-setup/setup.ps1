# =====================================================================
#  HomeLink House Guard - RedKryptonite one-shot installer
#  Run in an *Administrator* PowerShell on the laptop:
#    irm http://100.107.136.88:8080/guard-update/setup.ps1 | iex
#  (or double-click setup.bat if you copied this folder via USB)
# =====================================================================

$ErrorActionPreference = 'Stop'
$PackageBase = 'http://100.107.136.88:8080/guard-update'   # Alienware PC hosting the files
$InstallDir  = 'C:\HomeLink\backend'
$GuardFiles  = @('camera_server.py', 'camera_requirements.txt', 'start_guard.bat')

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }

$identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Administrator rights needed - a popup will appear. Click YES." -ForegroundColor Yellow
    $tmp = Join-Path $env:TEMP 'homelink-setup.ps1'
    if ($PSCommandPath) {
        Copy-Item $PSCommandPath $tmp -Force
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/setup.ps1" -OutFile $tmp
    }
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$tmp`""
    Write-Host "Continuing in the new (elevated) window..."
    return
}

Step "1/7 Getting House Guard files"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { $null }
foreach ($f in $GuardFiles) {
    $target = Join-Path $InstallDir $f
    if ($scriptDir -and (Test-Path (Join-Path $scriptDir $f))) {
        Copy-Item (Join-Path $scriptDir $f) $target -Force
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri "$PackageBase/$f" -OutFile $target
    }
}
Ok "Files in $InstallDir"

Step "2/7 Installing Tailscale"
$tsExe = "$env:ProgramFiles\Tailscale\tailscale.exe"
if (Test-Path $tsExe) {
    Ok "Tailscale already installed"
} else {
    $installed = $false
    try {
        winget install --id Tailscale.Tailscale -e --silent --accept-package-agreements --accept-source-agreements
        if (Test-Path $tsExe) { $installed = $true }
    } catch { }
    if (-not $installed) {
        Warn "winget failed - downloading installer from tailscale.com"
        $tsSetup = "$env:TEMP\tailscale-setup.exe"
        Invoke-WebRequest -UseBasicParsing -Uri 'https://pkgs.tailscale.com/stable/tailscale-setup-full.exe' -OutFile $tsSetup
        Start-Process $tsSetup -Wait   # follow the installer window on the TV
    }
    Ok "Tailscale installed"
}

Step "3/7 Joining your Tailscale network"
Write-Host "  A browser window will open - SIGN IN with the SAME account as on"
Write-Host "  the Alienware and your phone (ikeepsitrealz@gmail.com)." -ForegroundColor Yellow
Start-Process $tsExe -ArgumentList 'up' -NoNewWindow -Wait -ErrorAction SilentlyContinue
$tsIp = (& $tsExe ip -4 2>$null | Select-Object -First 1)
if ($tsIp) { Ok "This laptop's Tailscale IP: $tsIp" } else { Warn "Not signed in yet - finish the browser login, this can be done later." }

Step "4/7 Installing Python"
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python -and ((& python --version) -match 'Python 3')) {
    Ok "Python already installed: $(& python --version)"
} else {
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --override "/quiet InstallAllUsers=1 PrependPath=1"
    $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    Ok "Python installed: $(& python --version)"
}

Step "5/7 Installing camera server dependencies"
& python -m pip install -r (Join-Path $InstallDir 'camera_requirements.txt') --quiet
Ok "fastapi + uvicorn + opencv ready"

Step "6/7 Keep-awake settings (broken screen / closed lid)"
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
Ok "Laptop will stay awake while plugged in; closing the lid does nothing"

Step "7/7 Auto-start on boot + launching the guard"
$startup = [Environment]::GetFolderPath('Startup')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startup 'HomeLink House Guard.lnk'))
$shortcut.TargetPath = Join-Path $InstallDir 'start_guard.bat'
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Save()
Start-Process (Join-Path $InstallDir 'start_guard.bat') -WorkingDirectory $InstallDir
Ok "Guard starting now (webcam light should come on) and will auto-start on boot"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "  DONE! " -ForegroundColor Green
if ($tsIp) {
    Write-Host "  In the HomeLink app: Settings -> House Guard Camera ->"
    Write-Host "  http://${tsIp}:7171" -ForegroundColor Cyan
} else {
    Write-Host "  Finish the Tailscale browser sign-in, then run:  tailscale ip -4"
    Write-Host "  and put http://THAT-IP:7171 in the HomeLink app settings."
}
Write-Host "  If Windows Firewall pops up asking about Python," -ForegroundColor Yellow
Write-Host "  check BOTH boxes and click 'Allow access'." -ForegroundColor Yellow
Write-Host "=============================================="
