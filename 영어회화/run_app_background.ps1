param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

function Get-LanIp {
    try {
        $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4Address -ne $null } | Select-Object -First 1
        if ($cfg -and $cfg.IPv4Address) {
            return $cfg.IPv4Address.IPAddress
        }
        return $null
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

$dataDir = Join-Path $scriptDir "data"
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

$pidPath = Join-Path $dataDir "server.pid.json"
$stdoutPath = Join-Path $dataDir "server.out.log"
$stderrPath = Join-Path $dataDir "server.err.log"

if (Test-Path -LiteralPath $pidPath) {
    try {
        $meta = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        $existing = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "Server is already running in background."
            Write-Host "PID: $($meta.pid) | Port: $($meta.port)"
            Write-Host "Stop with: stop_app_background.bat"
            exit 0
        }
    } catch {
        # Ignore stale metadata.
    }
}

# Ensure venv and dependencies are ready.
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir "run_app.ps1") -Port $Port -SetupOnly | Out-Host

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment python not found: $venvPython"
}

if (Test-Path -LiteralPath $stdoutPath) { Remove-Item -LiteralPath $stdoutPath -Force }
if (Test-Path -LiteralPath $stderrPath) { Remove-Item -LiteralPath $stderrPath -Force }

$args = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
$proc = Start-Process -FilePath $venvPython `
    -ArgumentList $args `
    -WorkingDirectory $scriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

Start-Sleep -Milliseconds 700

if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
    throw "Failed to start background server. Check logs: $stderrPath"
}

$metaOut = @{
    pid = $proc.Id
    port = $Port
    started_at = (Get-Date).ToString("s")
}
$metaOut | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding UTF8

$lanIp = Get-LanIp
$tailIp = Get-TailscaleIp

Write-Host ""
Write-Host "Background server started."
Write-Host "PID: $($proc.Id)"
Write-Host "Open on this PC: http://localhost:$Port"
if ($lanIp) {
    Write-Host "Open on phone (same Wi-Fi): http://$($lanIp):$Port"
}
if ($tailIp) {
    Write-Host "Open outside (Tailscale): http://$($tailIp):$Port"
}
Write-Host ""
Write-Host "Logs:"
Write-Host "  OUT: $stdoutPath"
Write-Host "  ERR: $stderrPath"
Write-Host "Stop with: stop_app_background.bat"
