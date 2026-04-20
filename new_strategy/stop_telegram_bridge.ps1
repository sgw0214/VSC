Set-Location "E:\VSC\CODE"

$scriptPath = [System.IO.Path]::GetFullPath("E:\VSC\CODE\new_strategy\run_telegram_bridge.ps1")
$logDir = "E:\VSC\python\new_strategy\output\strategy_v2\telegram_bridge"
$stopLogPath = Join-Path $logDir "bridge_stop.log"

function Write-StopLog([string]$message) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Add-Content -Path $stopLogPath -Value ("[{0}] {1}" -f (Get-Date -Format "s"), $message)
}

$wrapperTargets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'powershell' -and
    $_.CommandLine -like "*$scriptPath*"
}
foreach ($target in $wrapperTargets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped telegram wrapper pid=" + $target.ProcessId)
    Write-StopLog ("wrapper_stopped pid={0}" -f $target.ProcessId)
}

$pythonTargets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'python' -and
    $_.CommandLine -like '*new_strategy.telegram_bridge_service*'
}
foreach ($target in $pythonTargets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped telegram bridge process pid=" + $target.ProcessId)
    Write-StopLog ("python_stopped pid={0}" -f $target.ProcessId)
}

