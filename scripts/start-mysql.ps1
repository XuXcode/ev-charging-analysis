param([string]$ServerHome = $env:MYSQL_SERVER_HOME)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataPath = Join-Path $projectRoot 'backend\.runtime\mysql'
if (-not $ServerHome) { $ServerHome = 'R:\Program Files\MySQL\MySQL Server 8.4' }
$serverPath = Join-Path $ServerHome 'bin\mysqld.exe'
if (-not (Test-Path -LiteralPath $serverPath)) { throw 'Set MYSQL_SERVER_HOME to the installed MySQL 8 directory.' }
if (-not (Test-Path -LiteralPath (Join-Path $dataPath 'auto.cnf'))) {
    throw 'Existing local database not found. Configure your own MySQL service following backend/README.md. This script never initializes data.'
}
if (Get-NetTCPConnection -LocalPort 23306 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'Port 23306 is already listening. Check the existing database; no second instance started.'
    exit 0
}
& $serverPath --no-defaults "--basedir=$ServerHome" "--datadir=$dataPath" --bind-address=127.0.0.1 --port=23306 --mysqlx=OFF --innodb-buffer-pool-size=67108864 --console
exit $LASTEXITCODE
