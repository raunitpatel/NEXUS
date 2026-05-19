# nexus/scripts/test-all.ps1

$ErrorActionPreference = "Stop"

Write-Host "Running NEXUS test suite..." -ForegroundColor Cyan

# =========================================================
# Infrastructure tests
# =========================================================

Write-Host ""
Write-Host "Running infrastructure integration tests..." -ForegroundColor Yellow

python -m pytest tests/integration/test_infra.py -v

# =========================================================
# Database schema tests
# =========================================================

Write-Host ""
Write-Host "Running database schema tests..." -ForegroundColor Yellow

python -m pytest db/tests/test_schema.py -v

# =========================================================
# Gateway service tests
# =========================================================

Write-Host ""
Write-Host "Finding nexus-gateway container..." -ForegroundColor Yellow

$gatewayContainer = docker ps `
    --filter "name=nexus-gateway" `
    --format "{{.ID}}"

if (-not $gatewayContainer) {
    Write-Host "[ERROR] nexus-gateway container is not running." -ForegroundColor Red
    exit 1
}

Write-Host "Gateway container: $gatewayContainer" -ForegroundColor Green

Write-Host ""
Write-Host "Running gateway async tests inside container..." -ForegroundColor Yellow

docker exec -it $gatewayContainer `
    python -m pytest tests/ -v --asyncio-mode=auto

# =========================================================
# Orchestrator service tests
# =========================================================

Write-Host ""
Write-Host "Finding nexus-orchestrator container..." -ForegroundColor Yellow

$orchestratorContainer = docker ps `
    --filter "name=nexus-orchestrator" `
    --format "{{.ID}}"

if (-not $orchestratorContainer) {
    Write-Host "[ERROR] nexus-orchestrator container is not running." -ForegroundColor Red
    exit 1
}

Write-Host "Orchestrator container: $orchestratorContainer" -ForegroundColor Green

Write-Host ""
Write-Host "Running orchestrator async tests inside container..." -ForegroundColor Yellow

docker exec -it $orchestratorContainer `
    python -m pytest tests/ -v --asyncio-mode=auto

Write-Host ""
Write-Host "All tests completed." -ForegroundColor Green


# =========================================================
# Search Agent service tests
# =========================================================

Write-Host ""
Write-Host "Finding nexus-search-agent container..." -ForegroundColor Yellow

$searchAgentContainer = docker ps `
    --filter "name=nexus-search-agent" `
    --format "{{.ID}}"

if (-not $searchAgentContainer) {
    Write-Host "[ERROR] nexus-search-agent container is not running." -ForegroundColor Red
    exit 1
}

Write-Host "Search Agent container: $searchAgentContainer" -ForegroundColor Green

Write-Host ""
Write-Host "Running search agent async tests inside container..." -ForegroundColor Yellow

docker exec -it $searchAgentContainer `
    python -m pytest tests/ -v --asyncio-mode=auto

