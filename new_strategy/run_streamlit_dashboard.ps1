Set-Location "E:\VSC\CODE"

$stdout = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v1\streamlit_stdout.log"
$stderr = "C:\Users\sgw02\OneDrive\python\new_strategy\output\strategy_v1\streamlit_stderr.log"

$existing = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue

if ($existing) {
    Write-Output "streamlit already running"
    exit 0
}

Start-Process -FilePath "python" `
    -ArgumentList @("-m", "streamlit", "run", "E:\VSC\CODE\new_strategy\streamlit_app.py", "--server.headless=true", "--server.port=8501") `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr

Write-Output "streamlit started"
