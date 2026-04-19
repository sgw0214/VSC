$taskName = "TodoDailyReminder"
$exePath = Join-Path $PSScriptRoot "dist\ToDoList.exe"

if (Test-Path $exePath) {
    $taskCommand = "`"$exePath`""
} else {
    $pythonPath = (Get-Command python).Source
    $pythonwPath = Join-Path (Split-Path $pythonPath -Parent) "pythonw.exe"
    $scriptPath = Join-Path $PSScriptRoot "main.py"
    $taskCommand = "`"$pythonwPath`" `"$scriptPath`""
}

schtasks /Create /SC DAILY /TN $taskName /TR $taskCommand /ST 08:00 /F
