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

Write-Host "Building nexus-gateway..." -ForegroundColor Yellow

docker build `
    -f services/gateway/Dockerfile `
    -t nexus-gateway .

Write-Host "Running nexus-gateway..." -ForegroundColor Yellow

docker rm -f nexus-gateway 2>$null

docker run -d `
    --name nexus-gateway `
    --network agent-net `
    --env-file services/gateway/.env `
    -p 8000:8000 `
    nexus-gateway

# =========================
# Future Services
# Uncomment when implemented
# =========================

# docker build `
#     -f services/orchestrator/Dockerfile `
#     -t nexus-orchestrator .
#
# docker rm -f nexus-orchestrator 2>$null
#
# docker run -d `
#     --name nexus-orchestrator `
#     --network agent-net `
#     --env-file services/orchestrator/.env `
#     -p 8001:8001 `
#     nexus-orchestrator

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
#     nexus-search-agent

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
#     nexus-memory-agent

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
#     nexus-tool-agent

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
#     nexus-code-agent

Write-Host ""
Write-Host "NEXUS services started." -ForegroundColor Green
Write-Host "  Gateway : http://localhost:8000/docs" -ForegroundColor DarkGray