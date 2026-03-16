Set-Location "E:\VSC\CODE"

$taskNames = @(
    "new_strategy_telegram_bridge",
    "new_strategy_market_schedule",
    "new_strategy_streamlit"
)

foreach ($taskName in $taskNames) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}

Get-ScheduledTask | Where-Object { $_.TaskName -like "new_strategy_*" } | Select-Object TaskName, State
