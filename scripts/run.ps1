$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath .venv\Scripts\python.exe)) {
    throw "Virtual environment not found. Run scripts/setup.ps1 first."
}

$PortProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 8000)
$PortProbe.Server.ExclusiveAddressUse = $true
try {
    $PortProbe.Start()
} catch {
    throw "Port 8000 is already in use. Stop the existing application with Ctrl+C in its terminal before running npm run dev again."
} finally {
    $PortProbe.Stop()
}

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
exit $LASTEXITCODE

