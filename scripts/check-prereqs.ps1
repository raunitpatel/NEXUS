# nexus/scripts/check-prereqs.ps1
# Verifies all prerequisites for NEXUS development on Windows 11.
# Run: .\scripts\check-prereqs.ps1

$ErrorActionPreference = "Continue"
$allPassed = $true

function Test-Prereq {
    param(
        [string]$Name,
        [scriptblock]$Test,
        [string]$FixHint
    )
    try {
        $result = & $Test
        if ($result) {
            Write-Host "  [PASS] $Name" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] $Name - $FixHint" -ForegroundColor Red
            $script:allPassed = $false
        }
    } catch {
        Write-Host "  [FAIL] $Name - $FixHint" -ForegroundColor Red
        $script:allPassed = $false
    }
}

Write-Host "`nNEXUS Prerequisites Check" -ForegroundColor Cyan
Write-Host "─────────────────────────" -ForegroundColor Cyan

# Docker Desktop
Test-Prereq "Docker Desktop running" {
    $null = docker info 2>&1
    $LASTEXITCODE -eq 0
} "Start Docker Desktop"

# Docker Compose v2
Test-Prereq "Docker Compose v2" {
    $version = docker compose version 2>&1
    $version -match "v2\."
} "Update Docker Desktop to 4.25+"

# PowerShell 7
Test-Prereq "PowerShell 7" {
    $PSVersionTable.PSVersion.Major -ge 7
} "Install PowerShell 7: winget install Microsoft.PowerShell"

# Python 3.11
Test-Prereq "Python 3.11" {
    $ver = python --version 2>&1
    $ver -match "3\.11"
} "Install Python 3.11 via pyenv-win"

# Node 20 LTS
Test-Prereq "Node 20 LTS" {
    $ver = node --version 2>&1
    $ver -match "v20\."
} "Install Node 20 via nvm-windows"

# git LF config
Test-Prereq "git core.autocrlf=false" {
    $val = git config --global core.autocrlf
    $val -eq "false"
} "Run: git config --global core.autocrlf false"

# Ports available
$requiredPorts = @(5434, 6379, 9092, 2181, 8080)
foreach ($port in $requiredPorts) {
    Test-Prereq "Port $port available" {
        $connections = netstat -an | Select-String ":$port\s"
        $null -eq $connections
    } "Stop the process using port $port"
}

Write-Host ""
if ($allPassed) {
    Write-Host "All prerequisites satisfied. Ready to run NEXUS." -ForegroundColor Green
} else {
    Write-Host "Some prerequisites failed. Fix the issues above before continuing." -ForegroundColor Red
    exit 1
}