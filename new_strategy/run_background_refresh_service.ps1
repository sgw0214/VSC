param(
    [switch]$Wrapper
)

Set-Location "E:\VSC\CODE"

$pythonExe = "e:\Miniconda3\python.exe"
$scriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
$logDir = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2"
$stdout = Join-Path $logDir "background_refresh_service.log"
$wrapperLog = Join-Path $logDir "background_refresh_wrapper.log"
$statePath = Join-Path $logDir "background_refresh_wrapper_state.json"
$restartDelaySeconds = 5
$appArgs = @(
    "-m",
    "new_strategy.run_market_schedule_service",
    "--poll-seconds", "60",
    "--intraday-open", "08:10",
    "--intraday-close", "20:00",
    "--intraday-interval-minutes", "30",
    "--trend-time", "06:00",
    "--trend-retry-interval-minutes", "30",
    "--eod-time", "20:10"
)

function Write-WrapperLog([string]$message) {
    Add-Content -Path $wrapperLog -Value ("[{0}] {1}" -f (Get-Date -Format "s"), $message)
}

function Write-State(
    [string]$status,
    [int]$childPid = 0,
    [int]$exitCode = 0,
    [string]$lastError = "",
    [int]$restartCount = 0
) {
    $payload = [ordered]@{
        wrapper_pid = $PID
        child_pid = $childPid
        status = $status
        restart_count = $restartCount
        updated_at = (Get-Date).ToString("s")
        last_exit_code = $exitCode
        last_error = $lastError
    }
    $payload | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8
}

function Get-SchedulerProcess {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match 'python' -and
        $_.CommandLine -like '*new_strategy.run_market_schedule_service*'
    }
}

function Get-WrapperProcess {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.Name -match 'powershell' -and
        $_.CommandLine -like "*$scriptPath*" -and
        $_.CommandLine -like "*-Wrapper*"
    }
}

function Stop-StaleSchedulerProcesses {
    $wrappers = @(Get-WrapperProcess)
    foreach ($wrapper in $wrappers) {
        Stop-Process -Id $wrapper.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("killed_stale_wrapper pid={0}" -f $wrapper.ProcessId)
    }

    $targets = @(Get-SchedulerProcess)
    foreach ($target in $targets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("killed_stale_child pid={0}" -f $target.ProcessId)
    }
}

if (-not $Wrapper) {
    if (-not $env:NEW_STRATEGY_TELEGRAM_BOT_TOKEN) {
        throw "Set NEW_STRATEGY_TELEGRAM_BOT_TOKEN before running this script."
    }
    if (-not $env:NEW_STRATEGY_TELEGRAM_CHAT_ID) {
        throw "Set NEW_STRATEGY_TELEGRAM_CHAT_ID before running this script."
    }
    if (-not $env:NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS) {
        $env:NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS = $env:NEW_STRATEGY_TELEGRAM_CHAT_ID
    }
    $env:NEW_STRATEGY_NOTIFIER_CHANNELS = "telegram"

    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $children = @(Get-SchedulerProcess)
    if ($children.Count -gt 0) {
        Write-Output "background refresh already running"
        exit 0
    }

    $wrappers = @(Get-WrapperProcess)
    if ($wrappers.Count -gt 0) {
        Write-WrapperLog "stale_wrapper_detected"
        Stop-StaleSchedulerProcesses
        Start-Sleep -Seconds 2
    }

    $powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $wrapperCmd = '"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $scriptPath + '" -Wrapper'
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = $wrapperCmd}
    if ($created.ReturnValue -ne 0) {
        throw ("Failed to start background refresh wrapper. ReturnValue=" + $created.ReturnValue)
    }

    Write-Output "background refresh wrapper started"
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Write-WrapperLog "wrapper_started"
$restartCount = 0
Write-State -status "starting" -restartCount $restartCount

while ($true) {
    Write-WrapperLog ("launch attempt={0}" -f ($restartCount + 1))
    try {
        Write-State -status "running" -childPid 0 -restartCount $restartCount
        & $pythonExe @appArgs *>> $stdout
        $exitCode = $LASTEXITCODE
        Write-WrapperLog ("child_exit exit_code={0}" -f $exitCode)
        Write-State -status "stopped" -childPid 0 -exitCode $exitCode -restartCount $restartCount
    } catch {
        $message = $_.Exception.Message
        Write-WrapperLog ("child_launch_error {0}" -f $message)
        Write-State -status "error" -childPid 0 -exitCode 1 -lastError $message -restartCount $restartCount
    }

    $restartCount += 1
    Start-Sleep -Seconds $restartDelaySeconds
}
