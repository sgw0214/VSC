if (-not $env:NEW_STRATEGY_HIDDEN_REFRESH) {
    $env:NEW_STRATEGY_HIDDEN_REFRESH = "1"
    Start-Process powershell `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath) `
        -WindowStyle Hidden
    exit 0
}

Set-Location "E:\VSC\CODE"

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

$logDir = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v1"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

python -m new_strategy.run_market_schedule_service --poll-seconds 60 --intraday-open 08:00 --intraday-close 20:00 --intraday-interval-minutes 30 --preclose-time 15:20 --eod-time 16:10 --krx-reconcile-time 21:00 --live-quotes "C:\Users\sgw02\OneDrive\python\new_strategy\live_quotes.csv" *>> (Join-Path $logDir "background_refresh_service.log")
