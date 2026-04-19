Set-Location "E:\VSC\CODE"

$scriptPath = [System.IO.Path]::GetFullPath("E:\VSC\CODE\new_strategy\run_background_refresh_service.ps1")
$statePath = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\background_refresh_wrapper_state.json"
$wrapperLog = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\background_refresh_wrapper.log"

function Write-StopLog([string]$message) {
    Add-Content -Path $wrapperLog -Value ("[{0}] {1}" -f (Get-Date -Format "s"), $message)
}

$wrapperTargets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'powershell' -and
    $_.CommandLine -like "*$scriptPath*" -and
    $_.CommandLine -like "*-Wrapper*"
}
foreach ($target in $wrapperTargets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped background refresh wrapper pid=" + $target.ProcessId)
    Write-StopLog ("wrapper_stopped pid={0}" -f $target.ProcessId)
}

$pythonTargets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'python' -and
    $_.CommandLine -like '*new_strategy.run_market_schedule_service*'
}
foreach ($target in $pythonTargets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped background refresh process pid=" + $target.ProcessId)
    Write-StopLog ("python_stopped pid={0}" -f $target.ProcessId)
}

if (Test-Path $statePath) {
    try {
        $payload = Get-Content $statePath -Raw | ConvertFrom-Json
        if ($payload.child_pid) {
            Stop-Process -Id ([int]$payload.child_pid) -Force -ErrorAction SilentlyContinue
            Write-Output ("stopped background refresh child pid=" + $payload.child_pid)
            Write-StopLog ("state_child_stopped pid={0}" -f $payload.child_pid)
        }
    } catch {
    }
    Remove-Item $statePath -Force -ErrorAction SilentlyContinue
}
