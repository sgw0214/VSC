param(
    [int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

function Get-LanIp {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceOperationalStatus Up |
            Where-Object {
                $_.IPAddress -ne "127.0.0.1" -and
                $_.IPAddress -notlike "169.254.*"
            } |
            Select-Object -First 1 -ExpandProperty IPAddress
        return $ip
    } catch {
        return $null
    }
}

function Get-TailscaleIp {
    try {
        if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
            return $null
        }
        $ip = (& tailscale ip -4 2>$null | Select-Object -First 1).Trim()
        if ([string]::IsNullOrWhiteSpace($ip)) {
            return $null
        }
        return $ip
    } catch {
        return $null
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python command not found. Install Python first."
}

$venvDir = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$requirements = Join-Path $scriptDir "requirements.txt"
$stampPath = Join-Path $venvDir ".requirements.sha256"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[1/4] Creating virtual environment..."
    & python -m venv $venvDir
}

$reqHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$needInstall = $true
if (Test-Path -LiteralPath $stampPath) {
    $savedHash = (Get-Content -LiteralPath $stampPath -Raw).Trim()
    if ($savedHash -eq $reqHash) {
        $needInstall = $false
    }
}

if ($needInstall) {
    Write-Host "[2/4] Installing dependencies..."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $requirements
    Set-Content -LiteralPath $stampPath -Value $reqHash -NoNewline
} else {
    Write-Host "[2/4] Dependencies are up to date."
}

Write-Host "[3/4] Environment ready."

$localUrl = "http://localhost:$Port"
$lanIp = Get-LanIp
$tailIp = Get-TailscaleIp

Write-Host ""
Write-Host "Open on this PC: $localUrl"
if ($lanIp) {
    Write-Host "Open on phone:  http://$($lanIp):$Port"
}
if ($tailIp) {
    Write-Host "Open outside (Tailscale): http://$($tailIp):$Port"
}
Write-Host ""

if ($SetupOnly) {
    Write-Host "[4/4] Setup-only mode complete."
    exit 0
}

if (-not $NoBrowser) {
    Start-Process $localUrl | Out-Null
}

Write-Host "[4/4] Starting server... (Press Ctrl+C to stop)"
& $venvPython -m uvicorn app.main:app --reload --host 0.0.0.0 --port $Port
