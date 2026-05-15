# nexus/scripts/start-infra.ps1
# Starts all NEXUS infrastructure containers and creates Kafka topics.
# Run from nexus/ root: .\scripts\start-infra.ps1

$ErrorActionPreference = "Stop"

Write-Host "Starting NEXUS infrastructure..." -ForegroundColor Cyan

# Verify .env exists
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env not found. Copy .env.example to .env and fill in values." -ForegroundColor Red
    exit 1
}

# Start all infra containers
docker compose up -d postgres redis zookeeper kafka jaeger prometheus nginx

Write-Host "Waiting for containers to become healthy..." -ForegroundColor Yellow

# Poll until all containers healthy (max 120 seconds)
$timeout = 120
$elapsed = 0
$services = @("nexus-postgres", "nexus-redis", "nexus-zookeeper", "nexus-kafka")

while ($elapsed -lt $timeout) {
    $allHealthy = $true
    foreach ($svc in $services) {
        $status = docker inspect --format "{{.State.Health.Status}}" $svc 2>&1
        if ($status -ne "healthy") {
            $allHealthy = $false
            break
        }
    }
    if ($allHealthy) { break }
    Start-Sleep -Seconds 5
    $elapsed += 5
    Write-Host "  Waiting... ($elapsed/$timeout s)" -ForegroundColor DarkGray
}

if ($elapsed -ge $timeout) {
    Write-Host "[ERROR] Containers did not become healthy within $timeout seconds." -ForegroundColor Red
    docker compose ps
    exit 1
}

Write-Host "All containers healthy. Creating Kafka topics..." -ForegroundColor Yellow

# Copy topic creation script into the kafka container and run it
docker compose cp infra/kafka/create_topics.sh kafka:/create_topics.sh
docker compose exec kafka /create_topics.sh
docker compose exec kafka /bin/bash /create_topics.sh

Write-Host ""
Write-Host "NEXUS infrastructure is ready." -ForegroundColor Green
Write-Host "  PostgreSQL : localhost:5434" -ForegroundColor DarkGray
Write-Host "  Redis      : localhost:6379" -ForegroundColor DarkGray
Write-Host "  Kafka      : localhost:29092 (external) / kafka:9092 (internal)" -ForegroundColor DarkGray
Write-Host "  Jaeger UI  : http://localhost:16686" -ForegroundColor DarkGray
Write-Host "  Prometheus : http://localhost:9090" -ForegroundColor DarkGray