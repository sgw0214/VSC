$pythonPath = (Get-Command python).Source
$pythonwPath = Join-Path (Split-Path $pythonPath -Parent) "pythonw.exe"
$scriptPath = Join-Path $PSScriptRoot "main.py"
$taskName = "TodoDailyReminder"
$taskCommand = "`"$pythonwPath`" `"$scriptPath`""

schtasks /Create /SC DAILY /TN $taskName /TR $taskCommand /ST 08:00 /F
