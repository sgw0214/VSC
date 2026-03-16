if (-not $env:NEW_STRATEGY_HIDDEN_BRIDGE) {
    $env:NEW_STRATEGY_HIDDEN_BRIDGE = "1"
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

$logDir = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v1\telegram_bridge"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

python -m new_strategy.telegram_bridge_service *>> (Join-Path $logDir "bridge_stdout.log")
