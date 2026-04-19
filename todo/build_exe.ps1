$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$mainScript = Join-Path $root "main.py"
$distDir = Join-Path $root "dist"
$buildDir = Join-Path $root "build"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name "ToDoList" `
  --distpath $distDir `
  --workpath $buildDir `
  --specpath $root `
  $mainScript
