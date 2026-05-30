$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataDir = Join-Path $env:APPDATA "wm2026"
$venvDir = Join-Path $dataDir ".venv"
$widgetDir = Join-Path $root "widget"

Write-Host "WM2026 Windows Installer"
Write-Host "------------------------"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

Copy-Item (Join-Path $root "engine.py") (Join-Path $dataDir "engine.py") -Force
Copy-Item (Join-Path $root "wm2026_server.py") (Join-Path $dataDir "wm2026_server.py") -Force
Copy-Item (Join-Path $root "sources.json") (Join-Path $dataDir "sources.json") -Force
Copy-Item (Join-Path $root "requirements.txt") (Join-Path $dataDir "requirements.txt") -Force

if (-not (Test-Path (Join-Path $dataDir "shift_config.json"))) {
  Copy-Item (Join-Path $root "shift_config.example.json") (Join-Path $dataDir "shift_config.example.json") -Force
}

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
  & py -3 -m venv $venvDir
  & (Join-Path $venvDir "Scripts\python.exe") -m pip install --upgrade pip
  & (Join-Path $venvDir "Scripts\python.exe") -m pip install -r (Join-Path $dataDir "requirements.txt")
} else {
  throw "Python Launcher 'py' wurde nicht gefunden. Bitte Python 3 installieren."
}

Write-Host ""
Write-Host "Fertig."
Write-Host "1. Lively Wallpaper installieren."
Write-Host "2. Den Ordner '$widgetDir' in Lively importieren."
Write-Host "3. Danach 'start_server.bat' oder 'start_server_hidden.vbs' ausfuehren."
