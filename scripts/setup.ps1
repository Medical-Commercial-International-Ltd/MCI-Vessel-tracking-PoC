$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12 or newer is required. Install it first, then rerun this script."
}

python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python virtual environment." }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip. Check network access and rerun setup." }
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,data]"
if ($LASTEXITCODE -ne 0) { throw "Failed to install application dependencies. Check the pip error above." }

if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}

Write-Host "Setup complete. Run scripts/run.ps1 and open http://127.0.0.1:8000"

