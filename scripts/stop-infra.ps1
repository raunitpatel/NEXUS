# nexus/scripts/stop-all.ps1
# Stops and removes all NEXUS containers.

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stopping NEXUS containers..." -ForegroundColor Cyan

# =========================
# Infrastructure Containers
# =========================

docker stop nexus-nginx
docker rm nexus-nginx

docker stop nexus-prometheus
docker rm nexus-prometheus

docker stop nexus-jaeger
docker rm nexus-jaeger

docker stop nexus-kafka
docker rm nexus-kafka

docker stop nexus-zookeeper
docker rm nexus-zookeeper

docker stop nexus-redis
docker rm nexus-redis

docker stop nexus-postgres
docker rm nexus-postgres

Write-Host ""
Write-Host "All NEXUS infrastructure containers stopped and removed." -ForegroundColor Green