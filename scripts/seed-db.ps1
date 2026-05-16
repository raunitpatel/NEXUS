# Verifies postgres container is healthy, installs db deps, runs seed

$ErrorActionPreference = "Stop"
$NexusRoot = Split-Path -Parent $PSScriptRoot
$EnvFile   = Join-Path $NexusRoot "db\.env"

Write-Host "[seed-db] Checking postgres container..." -ForegroundColor Cyan
$pgState = docker compose -f "$NexusRoot\docker-compose.yml" ps postgres --format json |
    ConvertFrom-Json |
    Select-Object -ExpandProperty State

if ($pgState -ne "running") {
    Write-Error "[seed-db] postgres container is not running. Run: .\scripts\start-infra.ps1"
    exit 1
}

# Load db/.env — never hardcode credentials in source
if (-Not (Test-Path $EnvFile)) {
    Write-Error "[seed-db] db\.env not found. Copy db\.env.example to db\.env and fill in your credentials."
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match "^\s*$" -or $_ -match "^\s*#") { return }
    $parts = $_ -split "=", 2
    if ($parts.Length -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
}

if (-Not $env:DATABASE_URL_LOCAL) {
    Write-Error "[seed-db] DATABASE_URL_LOCAL not found in db\.env."
    exit 1
}

Write-Host "[seed-db] Installing db dependencies..." -ForegroundColor Cyan
python -m pip install -r "$NexusRoot\db\requirements.txt" --quiet

Write-Host "[seed-db] Running seed script..." -ForegroundColor Cyan
python "$NexusRoot\db\seed.py"

if ($LASTEXITCODE -ne 0) {
    Write-Error "[seed-db] Seed script failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "[seed-db] Seed complete." -ForegroundColor Green
# --- AGNT-004: end ---