Set-Location "E:\VSC\CODE"

$commonSettingsArgs = @{
    AllowStartIfOnBatteries = $true
    DontStopIfGoingOnBatteries = $true
    MultipleInstances = "IgnoreNew"
}

$taskDefs = @(
    @{
        Name = "new_strategy_live_quotes"
        Script = "E:\VSC\CODE\new_strategy\run_kiwoom_live_quotes.ps1"
        Description = "Start new_strategy live quotes collector at logon"
    },
    @{
        Name = "new_strategy_telegram_bridge"
        Script = "E:\VSC\CODE\new_strategy\run_telegram_bridge.ps1"
        Description = "Start new_strategy telegram bridge at logon"
        SettingsArgs = @{
            StartWhenAvailable = $true
            RestartCount = 999
            RestartInterval = (New-TimeSpan -Minutes 1)
            ExecutionTimeLimit = ([TimeSpan]::Zero)
        }
    },
    @{
        Name = "new_strategy_market_schedule"
        Script = "E:\VSC\CODE\new_strategy\run_background_refresh_service.ps1"
        Description = "Start new_strategy market schedule service at logon"
    },
    @{
        Name = "new_strategy_streamlit"
        Script = "E:\VSC\CODE\new_strategy\run_streamlit_dashboard.ps1"
        Description = "Start new_strategy streamlit dashboard at logon"
    }
)

$userId = $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest

foreach ($task in $taskDefs) {
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
    $taskSettingsArgs = @{}
    if ($task.ContainsKey("SettingsArgs") -and $task.SettingsArgs) {
        $taskSettingsArgs = $task.SettingsArgs
    }
    $settingsArgs = @{} + $commonSettingsArgs + $taskSettingsArgs
    $settings = New-ScheduledTaskSettingsSet @settingsArgs
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$($task.Script)`""
    Register-ScheduledTask `
        -TaskName $task.Name `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description $task.Description `
        -Force | Out-Null
}

Get-ScheduledTask | Where-Object { $_.TaskName -like "new_strategy_*" } | Select-Object TaskName, State
