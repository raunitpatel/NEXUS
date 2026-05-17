# nexus/scripts/stop-all.ps1
# Stops and removes all NEXUS containers.

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stopping NEXUS containers..." -ForegroundColor Cyan

# =========================
# Application Services
# =========================

docker stop nexus-gateway
docker rm nexus-gateway

# Future services
docker stop nexus-orchestrator
docker rm nexus-orchestrator

docker stop nexus-search-agent
docker rm nexus-search-agent

docker stop nexus-memory-agent
docker rm nexus-memory-agent

docker stop nexus-tool-agent
docker rm nexus-tool-agent

docker stop nexus-code-agent
docker rm nexus-code-agent


Write-Host ""
Write-Host "All NEXUS services containers stopped and removed." -ForegroundColor Green