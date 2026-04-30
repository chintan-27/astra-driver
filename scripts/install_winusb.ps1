# install_winusb.ps1
# Binds WinUSB to the Orbbec Astra Pro depth/IR sensor (VID 2BC5, PID 0403).
# Must be run once as Administrator. After this, astra-ir-view works as a normal user.
#
# Usage (from an elevated PowerShell prompt):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\install_winusb.ps1

$ErrorActionPreference = "Stop"

$VID    = "2BC5"
$PID    = "0403"
$NAME   = "Orbbec Astra Pro Depth/IR"
$ZADIG  = "$env:TEMP\zadig.exe"
$ZADIG_URL = "https://github.com/pbatard/zadig/releases/download/v2.9/zadig-2.9.exe"

Write-Host ""
Write-Host "Orbbec Astra Pro — WinUSB setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# ── Check admin ───────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent() `
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "Right-click PowerShell → 'Run as administrator', then try again."
    exit 1
}

# ── Check device is connected ─────────────────────────────────────────────────
Write-Host "Looking for device VID_${VID}&PID_${PID}..." -NoNewline
$device = Get-PnpDevice -ErrorAction SilentlyContinue |
          Where-Object { $_.InstanceId -match "VID_${VID}.*PID_${PID}" } |
          Select-Object -First 1

if ($null -eq $device) {
    Write-Host " NOT FOUND" -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure the Orbbec Astra Pro is plugged in, then run this script again."
    exit 1
}
Write-Host " found: $($device.FriendlyName)" -ForegroundColor Green

# ── Check if WinUSB is already bound ─────────────────────────────────────────
if ($device.DriverProvider -match "Microsoft" -and $device.Service -match "WinUSB|libusbK") {
    Write-Host ""
    Write-Host "WinUSB is already installed for this device." -ForegroundColor Green
    Write-Host "You can use 'pip install orbbec-astra-raw[viewer]' and run 'astra-ir-view'."
    exit 0
}

# ── Download Zadig ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Downloading Zadig..." -NoNewline
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $ZADIG_URL -OutFile $ZADIG -UseBasicParsing
    Write-Host " done" -ForegroundColor Green
} catch {
    Write-Host " FAILED" -ForegroundColor Red
    Write-Host "Download Zadig manually from https://zadig.akeo.ie/ and run it."
    exit 1
}

# ── Write Zadig INI for silent install ────────────────────────────────────────
$ini = @"
[Zadig]
LogLevel=0
DefaultDriver=WinUSB

[Device]
Description=$NAME
VID=0x${VID}
PID=0x${PID}
"@

$iniPath = "$env:TEMP\zadig_astra.ini"
$ini | Out-File -FilePath $iniPath -Encoding ascii

# ── Run Zadig ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installing WinUSB driver via Zadig..." -ForegroundColor Yellow
Write-Host "(A Zadig window will open. Select 'Orbbec Astra Pro' and click 'Install Driver')"
Write-Host ""

Start-Process -FilePath $ZADIG -ArgumentList "--ini=$iniPath" -Wait

# ── Verify ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Checking installation..." -NoNewline
Start-Sleep -Seconds 2

$device = Get-PnpDevice -ErrorAction SilentlyContinue |
          Where-Object { $_.InstanceId -match "VID_${VID}.*PID_${PID}" } |
          Select-Object -First 1

if ($device -and $device.Status -eq "OK") {
    Write-Host " OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "Done! You can now use the driver as a normal user:" -ForegroundColor Green
    Write-Host "  pip install orbbec-astra-raw[viewer]"
    Write-Host "  astra-ir-view"
} else {
    Write-Host ""
    Write-Host "Could not confirm. If Zadig showed success, unplug/replug the camera and try again."
    Write-Host "If it failed, open Zadig manually (zadig.akeo.ie), select the Astra device, and install WinUSB."
}

# ── Cleanup ───────────────────────────────────────────────────────────────────
Remove-Item $ZADIG -ErrorAction SilentlyContinue
Remove-Item $iniPath -ErrorAction SilentlyContinue
