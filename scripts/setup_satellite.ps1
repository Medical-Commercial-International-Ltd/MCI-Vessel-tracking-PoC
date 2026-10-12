param([string]$PythonPath = "")
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not $PythonPath) {
    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313-arm64\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "C:\Python313\python.exe"
    )
    $PythonPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $PythonPath) {
    throw "Install Python 3.13, then run this script with -PythonPath pointing to its python.exe."
}
if (-not (Test-Path -LiteralPath .venv-satellite\Scripts\python.exe)) {
    & $PythonPath -m venv .venv-satellite
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the satellite environment." }
}
& .\.venv-satellite\Scripts\python.exe -m pip install --only-binary=:all: -r scripts/satellite-requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Satellite dependency installation failed. Check the pip error above." }
Write-Host "Satellite imagery is ready. Restart npm run dev and choose GOES infrared (10 min, on demand)."
