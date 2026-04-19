Set-Location "E:\VSC\CODE"

$scriptPath = [System.IO.Path]::GetFullPath("E:\VSC\CODE\new_strategy\run_streamlit_dashboard.ps1")
$statePath = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\streamlit_wrapper_state.json"
$wrapperLog = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2\streamlit_wrapper.log"

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
    Write-Output ("stopped streamlit wrapper pid=" + $target.ProcessId)
    Write-StopLog ("wrapper_stopped pid={0}" -f $target.ProcessId)
}

$listenerTargets = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($listenerTargets) {
    ($listenerTargets | Select-Object -ExpandProperty OwningProcess -Unique) | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        Write-Output ("stopped streamlit pid=" + $_)
        Write-StopLog ("listener_stopped pid={0}" -f $_)
    }
}

$pythonTargets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like '*streamlit*streamlit_app.py*'
}
foreach ($target in $pythonTargets) {
    Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped streamlit process pid=" + $target.ProcessId)
    Write-StopLog ("python_stopped pid={0}" -f $target.ProcessId)
}

if (Test-Path $statePath) {
    try {
        $payload = Get-Content $statePath -Raw | ConvertFrom-Json
        if ($payload.child_pid) {
            Stop-Process -Id ([int]$payload.child_pid) -Force -ErrorAction SilentlyContinue
            Write-Output ("stopped streamlit child pid=" + $payload.child_pid)
            Write-StopLog ("state_child_stopped pid={0}" -f $payload.child_pid)
        }
    } catch {
    }
    Remove-Item $statePath -Force -ErrorAction SilentlyContinue
}
