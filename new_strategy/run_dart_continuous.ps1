$ErrorActionPreference = "Continue"

$workdir = "e:\VSC\CODE"
Set-Location $workdir

$apiKey = "e8a64572875ad1ee7bdf3690df2ead1ba141aa4f"
$dataRoot = if ($env:NEW_STRATEGY_DATA_ROOT) { $env:NEW_STRATEGY_DATA_ROOT } else { "E:\VSC\python\new_strategy" }
$logPath = Join-Path $dataRoot "dart_continuous.log"
$batch = 500

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    $line | Tee-Object -FilePath $logPath -Append
}

Write-Log "continuous runner started"

while ($true) {
    $cmd = @(
        "python", "new_strategy/fetch_fundamental_dart.py",
        "--api-key", $apiKey,
        "--price-panel", (Join-Path $dataRoot "price_panel.csv"),
        "--start-year", "2015",
        "--end-year", "2026",
        "--rpm", "90",
        "--sleep-sec", "0",
        "--max-requests", "$batch",
        "--raw-output", (Join-Path $dataRoot "fundamental_quarterly_raw.csv"),
        "--output", (Join-Path $dataRoot "fundamental_quarterly_multi.csv")
    )

    $output = & $cmd[0] $cmd[1..($cmd.Length - 1)] 2>&1
    $exitCode = $LASTEXITCODE
    $output | Tee-Object -FilePath $logPath -Append | Out-Null

    $planLine = $output | Where-Object { $_ -match "\[plan\] estimated_requests=" } | Select-Object -Last 1
    $savedLine = $output | Where-Object { $_ -match "\[saved\] new_strategy\\data\\fundamental_quarterly_multi_request_log\.csv rows=" } | Select-Object -Last 1

    if ($planLine) {
        if ($planLine -match "estimated_requests=([\d,]+)") {
            $remain = ($matches[1] -replace ",", "")
            Write-Log "batch done; estimated_requests=$remain; exit=$exitCode"
            if ([int]$remain -le 0) {
                Write-Log "all done; stopping continuous runner"
                break
            }
        } else {
            Write-Log "batch done; could not parse remain; exit=$exitCode"
        }
    } else {
        Write-Log "batch done; no plan line; exit=$exitCode"
    }

    if ($exitCode -ne 0) {
        Write-Log "non-zero exit detected; sleep 30s then retry"
        Start-Sleep -Seconds 30
    } else {
        Start-Sleep -Seconds 2
    }
}

