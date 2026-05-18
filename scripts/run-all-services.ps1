# nexus/scripts/run-all-services.ps1
# Builds and starts NEXUS application services.

$ErrorActionPreference = "Stop"

Write-Host "Starting NEXUS application services..." -ForegroundColor Cyan

# Ensure required infrastructure containers are running
$required = @(
    "nexus-postgres",
    "nexus-redis"
)

foreach ($svc in $required) {

    $running = docker inspect --format "{{.State.Running}}" $svc 2>$null

    if ($running -ne "true") {
        Write-Host "[ERROR] Required container '$svc' is not running." -ForegroundColor Red
        Write-Host "Run .\scripts\start-infra.ps1 first." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "Infrastructure verified." -ForegroundColor Green

# =========================
# Gateway Service
# =========================

Write-Host ""
Write-Host "Building nexus-gateway..." -ForegroundColor Yellow

docker build `
    -f services/gateway/Dockerfile `
    -t nexus-gateway .

Write-Host "Running nexus-gateway..." -ForegroundColor Yellow

docker rm -f nexus-gateway 2>$null

# Production
# docker run -d `
#     --name nexus-gateway `
#     --network agent-net `
#     --env-file services/gateway/.env `
#     -p 8000:8000 `
#     nexus-gateway

# Development
docker run -d `
    --name nexus-gateway `
    --network agent-net `
    --env-file services/gateway/.env `
    -p 8000:8000 `
    -v "${PWD}/services/gateway:/app" `
    -v "${PWD}/services/shared:/app/shared" `
    nexus-gateway `
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# =========================
# Orchestrator Service
# =========================

Write-Host ""
Write-Host "Building nexus-orchestrator..." -ForegroundColor Yellow

docker build `
    -f services/orchestrator/Dockerfile `
    -t nexus-orchestrator .

Write-Host "Running nexus-orchestrator..." -ForegroundColor Yellow

docker rm -f nexus-orchestrator 2>$null

# Production
# docker run -d `
#     --name nexus-orchestrator `
#     --network agent-net `
#     --env-file services/orchestrator/.env `
#     -p 8001:8001 `
#     nexus-orchestrator

# Development
docker run -d `
    --name nexus-orchestrator `
    --network agent-net `
    --env-file services/orchestrator/.env `
    -p 8001:8001 `
    -v "${PWD}/services/orchestrator:/app" `
    -v "${PWD}/services/shared:/app/shared" `
    nexus-orchestrator `
    uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# =========================
# Future Services
# Uncomment when implemented
# =========================

# =========================
# Search Agent
# =========================

# docker build `
#     -f services/search_agent/Dockerfile `
#     -t nexus-search-agent .
#
# docker rm -f nexus-search-agent 2>$null
#
# docker run -d `
#     --name nexus-search-agent `
#     --network agent-net `
#     --env-file services/search_agent/.env `
#     -p 8002:8002 `
#     -v "${PWD}/services/search_agent:/app" `
#     -v "${PWD}/services/shared:/app/shared" `
#     nexus-search-agent `
#     uvicorn main:app --host 0.0.0.0 --port 8002 --reload

# =========================
# Memory Agent
# =========================

# docker build `
#     -f services/memory_agent/Dockerfile `
#     -t nexus-memory-agent .
#
# docker rm -f nexus-memory-agent 2>$null
#
# docker run -d `
#     --name nexus-memory-agent `
#     --network agent-net `
#     --env-file services/memory_agent/.env `
#     -p 8003:8003 `
#     -v "${PWD}/services/memory_agent:/app" `
#     -v "${PWD}/services/shared:/app/shared" `
#     nexus-memory-agent `
#     uvicorn main:app --host 0.0.0.0 --port 8003 --reload

# =========================
# Tool Agent
# =========================

# docker build `
#     -f services/tool_agent/Dockerfile `
#     -t nexus-tool-agent .
#
# docker rm -f nexus-tool-agent 2>$null
#
# docker run -d `
#     --name nexus-tool-agent `
#     --network agent-net `
#     --env-file services/tool_agent/.env `
#     -p 8004:8004 `
#     -v "${PWD}/services/tool_agent:/app" `
#     -v "${PWD}/services/shared:/app/shared" `
#     nexus-tool-agent `
#     uvicorn main:app --host 0.0.0.0 --port 8004 --reload

# =========================
# Code Agent
# =========================

# docker build `
#     -f services/code_agent/Dockerfile `
#     -t nexus-code-agent .
#
# docker rm -f nexus-code-agent 2>$null
#
# docker run -d `
#     --name nexus-code-agent `
#     --network agent-net `
#     --env-file services/code_agent/.env `
#     -p 8005:8005 `
#     -v "${PWD}/services/code_agent:/app" `
#     -v "${PWD}/services/shared:/app/shared" `
#     nexus-code-agent `
#     uvicorn main:app --host 0.0.0.0 --port 8005 --reload

Write-Host ""
Write-Host "NEXUS services started." -ForegroundColor Green
Write-Host "  Gateway      : http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host "  Orchestrator : http://localhost:8001/docs" -ForegroundColor DarkGray