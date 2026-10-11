$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'
$pythonCandidates = @(
    (Join-Path $backendPath '.conda\python.exe'),
    (Join-Path $projectRoot '.venv\Scripts\python.exe')
)
$pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) {
    throw 'No Python interpreter found. Expected backend/.conda or root .venv.'
}
Set-Location -LiteralPath $backendPath
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
exit $LASTEXITCODE
