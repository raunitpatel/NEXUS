# nexus/scripts/stop-all.ps1
# Gracefully stops all NEXUS containers.
# Volumes are NOT removed (data persists).
# To also remove volumes: docker compose down --volumes
#
# Run from nexus/ root: .\scripts\stop-all.ps1

Write-Host "Stopping all NEXUS containers..." -ForegroundColor Cyan
docker compose down
Write-Host "All containers stopped. Volumes preserved." -ForegroundColor Green
Write-Host "To remove volumes: docker compose down --volumes" -ForegroundColor DarkGray