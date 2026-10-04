$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$pythonPath = Join-Path $backendPath '.conda\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Conda environment missing. Create backend/.conda using backend/environment.yml.'
}
Set-Location -LiteralPath $backendPath
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
exit $LASTEXITCODE
