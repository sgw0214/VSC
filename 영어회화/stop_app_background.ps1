$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidPath = Join-Path $scriptDir "data\server.pid.json"

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Host "No background server metadata found."
    exit 0
}

try {
    $meta = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
} catch {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Removed invalid server metadata."
    exit 0
}

$procId = [int]$meta.pid
$proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
if ($proc) {
    Stop-Process -Id $procId -Force
    Write-Host "Stopped background server. PID: $procId"
} else {
    Write-Host "Background server process not running. PID: $procId"
}

Remove-Item -LiteralPath $pidPath -Force
