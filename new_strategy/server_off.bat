@echo off
setlocal
cd /d "%~dp0"
echo [1/4] live quotes stopping...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_kiwoom_live_quotes.ps1"

echo [2/4] background refresh stopping...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_background_refresh_service.ps1"

echo [3/4] streamlit dashboard stopping...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_streamlit_dashboard.ps1"

echo [4/4] telegram bridge stopping...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_telegram_bridge.ps1"

echo all services stop command sent.
endlocal
