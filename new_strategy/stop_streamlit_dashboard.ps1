Set-Location "E:\VSC\CODE"

$targets = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue

if (-not $targets) {
    Write-Output "streamlit not running"
    exit 0
}

($targets | Select-Object -ExpandProperty OwningProcess -Unique) | ForEach-Object {
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    Write-Output ("stopped streamlit pid=" + $_)
}
