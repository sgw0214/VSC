@echo off
setlocal
cd /d "%~dp0"
echo [1/4] live quotes starting...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_kiwoom_live_quotes.ps1"

echo [2/4] background refresh starting...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_background_refresh_service.ps1"

echo [3/4] streamlit dashboard starting...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_streamlit_dashboard.ps1"

echo [4/4] telegram bridge starting...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_telegram_bridge.ps1"

echo all services start command sent.
endlocal
