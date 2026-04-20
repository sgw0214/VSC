if (-not $env:NEW_STRATEGY_HIDDEN_KIWOOM_QUOTES) {
    $env:NEW_STRATEGY_HIDDEN_KIWOOM_QUOTES = "1"
    Start-Process powershell `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath) `
        -WindowStyle Hidden
    exit 0
}

Set-Location "E:\VSC\CODE"

$logDir = "E:\VSC\python\new_strategy\output\strategy_v2"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

python -m new_strategy.fetch_live_quotes_kiwoom_rest --interval-seconds 30 *>> (Join-Path $logDir "kiwoom_live_quotes.log")

