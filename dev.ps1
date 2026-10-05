# Starts the backend (in a new window) and the frontend (here), then opens the app in your browser.
# Usage, from the project folder:  .\dev.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# First-time setup
if (-not (Test-Path "$root\backend\.venv")) {
    Write-Host 'Setting up the Python environment (first run only)...'
    python -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\python" -m pip install -q -e "$root\backend[dev]"
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host 'Installing frontend packages (first run only)...'
    Push-Location "$root\frontend"; npm install; Pop-Location
}

# Backend in its own window so its logs stay visible
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "Set-Location '$root\backend'; `$Host.UI.RawUI.WindowTitle = 'LoL Survival backend'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
)

# Frontend here; --open launches the browser once Vite is ready
Set-Location "$root\frontend"
npm run dev -- --open
