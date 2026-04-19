param(
    [switch]$Wrapper
)

Set-Location "E:\VSC\CODE"

$pythonExe = "e:\Miniconda3\python.exe"
$appArgs = @(
    "-m",
    "streamlit",
    "run",
    "E:\VSC\CODE\new_strategy\streamlit_app.py",
    "--server.headless=true",
    "--server.address=0.0.0.0",
    "--server.port=8501"
)
$scriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
$appPath = "E:\VSC\CODE\new_strategy\streamlit_app.py"
$sourceDir = "E:\VSC\CODE\new_strategy"
$logDir = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v2"
$stdout = Join-Path $logDir "streamlit_stdout.log"
$stderr = Join-Path $logDir "streamlit_stderr.log"
$wrapperLog = Join-Path $logDir "streamlit_wrapper.log"
$statePath = Join-Path $logDir "streamlit_wrapper_state.json"
$restartDelaySeconds = 5
$sourceCheckSeconds = 5

function Get-StreamlitListener {
    return Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
}

function Test-StreamlitHealthy {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8501" -TimeoutSec 5
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
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

function Get-StreamlitPythonProcess {
    return Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match 'python' -and
        $_.CommandLine -like '*streamlit*streamlit_app.py*'
    }
}

function Stop-StaleStreamlitProcesses {
    $wrappers = @(Get-WrapperProcess)
    foreach ($wrapper in $wrappers) {
        Stop-Process -Id $wrapper.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("killed_stale_wrapper pid={0}" -f $wrapper.ProcessId)
    }

    $pythonTargets = @(Get-StreamlitPythonProcess)
    foreach ($target in $pythonTargets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("killed_stale_child pid={0}" -f $target.ProcessId)
    }

    $listeners = @(Get-StreamlitListener)
    foreach ($listener in $listeners) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("killed_stale_listener pid={0}" -f $listener.OwningProcess)
    }
}

function Stop-StreamlitChildProcesses {
    $pythonTargets = @(Get-StreamlitPythonProcess)
    foreach ($target in $pythonTargets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("child_python_stopped pid={0}" -f $target.ProcessId)
    }

    $listeners = @(Get-StreamlitListener)
    foreach ($listener in $listeners) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-WrapperLog ("child_listener_stopped pid={0}" -f $listener.OwningProcess)
    }
}

function Write-WrapperLog([string]$message) {
    Add-Content -Path $wrapperLog -Value ("[{0}] {1}" -f (Get-Date -Format "s"), $message)
}

function Get-StreamlitSourceToken {
    $latest = Get-ChildItem -Path $sourceDir -Filter "*.py" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notlike "*\__pycache__\*" -and
            $_.FullName -notlike "*\output\*" -and
            $_.FullName -notlike "*\.venv\*"
        } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1

    if (-not $latest) {
        return "missing-source"
    }
    return ("{0}|{1}" -f $latest.LastWriteTimeUtc.Ticks, $latest.FullName)
}

function Write-State(
    [string]$status,
    [int]$childPid = 0,
    [int]$exitCode = 0,
    [string]$lastError = "",
    [int]$restartCount = 0,
    [string]$sourceToken = ""
) {
    $payload = [ordered]@{
        wrapper_pid = $PID
        child_pid = $childPid
        status = $status
        restart_count = $restartCount
        updated_at = (Get-Date).ToString("s")
        last_exit_code = $exitCode
        last_error = $lastError
        source_token = $sourceToken
    }
    $tmpPath = "$statePath.tmp"
    $payload | ConvertTo-Json | Set-Content -Path $tmpPath -Encoding UTF8
    Move-Item -Path $tmpPath -Destination $statePath -Force
}

if (-not $Wrapper) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    $listener = @(Get-StreamlitListener)
    $wrappers = @(Get-WrapperProcess)
    $children = @(Get-StreamlitPythonProcess)
    $healthy = ($listener.Count -gt 0) -and (Test-StreamlitHealthy)
    $currentSourceToken = Get-StreamlitSourceToken
    $runningSourceToken = ""
    if (Test-Path $statePath) {
        try {
            $state = Get-Content $statePath -Raw | ConvertFrom-Json
            $runningSourceToken = [string]$state.source_token
        } catch {
            $runningSourceToken = ""
        }
    }
    $sourceChanged = $healthy -and $runningSourceToken -and ($runningSourceToken -ne $currentSourceToken)

    if ($healthy -and -not $sourceChanged) {
        Write-Output "streamlit already running"
        exit 0
    }

    if ($wrappers.Count -gt 0 -or $children.Count -gt 0 -or $listener.Count -gt 0) {
        if ($sourceChanged) {
            Write-WrapperLog "source_changed_instance_detected"
        }
        Write-WrapperLog "stale_or_unhealthy_instance_detected"
        Stop-StaleStreamlitProcesses
        Start-Sleep -Seconds 2
    }

    $powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $wrapperCmd = '"' + $powershellExe + '" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $scriptPath + '" -Wrapper'
    $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = $wrapperCmd}
    if ($created.ReturnValue -ne 0) {
        throw ("Failed to start streamlit wrapper. ReturnValue=" + $created.ReturnValue)
    }

    Write-Output "streamlit wrapper started"
    exit 0
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Write-WrapperLog "wrapper_started"
$restartCount = 0
Write-State -status "starting" -restartCount $restartCount -sourceToken (Get-StreamlitSourceToken)

while ($true) {
    $sourceToken = Get-StreamlitSourceToken
    Write-WrapperLog ("launch attempt={0}" -f ($restartCount + 1))
    try {
        $powershellExe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
        $childCommand = "& '$pythonExe' -m streamlit run '$appPath' --server.headless=true --server.address=0.0.0.0 --server.port=8501 1>> '$stdout' 2>> '$stderr'"
        $child = Start-Process -FilePath $powershellExe -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            $childCommand
        ) -WindowStyle Hidden -PassThru
        Write-WrapperLog ("child_started pid={0} source={1}" -f $child.Id, $sourceToken)
        Write-State -status "running" -childPid $child.Id -restartCount $restartCount -sourceToken $sourceToken

        while (-not $child.HasExited) {
            Start-Sleep -Seconds $sourceCheckSeconds
            $currentToken = Get-StreamlitSourceToken
            if ($currentToken -ne $sourceToken) {
                Write-WrapperLog ("source_changed_restart old={0} new={1}" -f $sourceToken, $currentToken)
                Write-State -status "restarting_source_changed" -childPid $child.Id -restartCount $restartCount -sourceToken $currentToken
                Stop-StreamlitChildProcesses
                Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
                break
            }
            $child.Refresh()
        }

        if ($child.HasExited) {
            $exitCode = $child.ExitCode
            Write-WrapperLog ("child_exit pid={0} exit_code={1}" -f $child.Id, $exitCode)
            Write-State -status "stopped" -childPid $child.Id -exitCode $exitCode -restartCount $restartCount -sourceToken $sourceToken
        }
    } catch {
        $message = $_.Exception.Message
        Write-WrapperLog ("child_launch_error {0}" -f $message)
        Write-State -status "error" -childPid 0 -exitCode 1 -lastError $message -restartCount $restartCount -sourceToken $sourceToken
    }

    $restartCount += 1
    Start-Sleep -Seconds $restartDelaySeconds
}
