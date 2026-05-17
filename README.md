# NEXUS — Dev Setup

## Prerequisites

| Tool | Version |
|---|---|
| Git | 2.40+ |
| Docker Desktop / Docker Engine | 4.25+ |
| Python | 3.11.9 (via pyenv) |
| Node | 20 LTS (via nvm) |
| PowerShell | 7+ (Windows only) |

---

## 1. Git — Disable CRLF (before cloning)

**Windows**
```powershell
git config --global core.autocrlf false
git config --global core.eol lf
```

**Linux**
```bash
git config --global core.autocrlf false
git config --global core.eol lf
```

---

## 2. Python 3.11.9 via pyenv

### Install pyenv

**Windows (pyenv-win)**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
Invoke-WebRequest -UseBasicParsing `
  -Uri "https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1" `
  -OutFile "$HOME\install-pyenv-win.ps1"
& "$HOME\install-pyenv-win.ps1"
# Restart PowerShell 7 after this
```

**Linux**
```bash
curl https://pyenv.run | bash

# Add to ~/.bashrc or ~/.zshrc
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc
```

### Install Python 3.11.9 and pin to project

**Windows + Linux (same commands)**
```bash
pyenv install 3.11.9

# Pin 3.11.9 to the nexus/ directory
# Creates a .python-version file — pyenv reads it automatically
# whenever you cd into nexus/
cd nexus
pyenv local 3.11.9

# Verify
python --version   # must show Python 3.11.9
```

> Every time you `cd nexus` pyenv switches to 3.11.9 automatically.
> No venv, no activation step needed.

---

## 3. Node 20 via nvm

**Windows**
```powershell
# Install nvm-windows from https://github.com/coreybutler/nvm-windows/releases
nvm install 20
nvm use 20
```

**Linux**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
```

---

## 4. Clone the repo

**Windows**
```powershell
git clone https://github.com/<your-handle>/nexus.git
cd nexus
python --version   # must show Python 3.11.9 (pyenv kicks in automatically)
```

**Linux**
```bash
git clone https://github.com/<your-handle>/nexus.git
cd nexus
python --version   # must show Python 3.11.9
```

---

## 5. Environment variables

### Root `.env` (infrastructure + all services)

**Windows**
```powershell
Copy-Item .env.example .env
code .env
```

**Linux**
```bash
cp .env.example .env
nano .env
```

### `db/.env` (seed script — runs on Windows host, outside Docker)

**Windows**
```powershell
Copy-Item db\.env.example db\.env
code db\.env
```

**Linux**
```bash
cp db/.env.example db/.env
nano db/.env
```

### Values to set

| Variable | File | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | `.env` | Set something strong |
| `REDIS_PASSWORD` | `.env` | Set something strong |
| `ANTHROPIC_API_KEY` | `.env` | From https://console.anthropic.com |
| `JWT_SECRET` | `.env` | Any random string, 32+ chars |
| `POSTGRES_PORT` | `.env` | Change to `5434` if port 5432 is taken |
| `NGINX_HOST_PORT` | `.env` | Change to `8080` if port 80 is taken |
| `DATABASE_URL_LOCAL` | `db/.env` | Must use host-mapped port (default `5434`) |

> `db/.env` is git-ignored — never commit it. It holds the host-side
> connection string used by `db/seed.py` and other CLI tools that run
> outside Docker. Services running inside Docker use `DATABASE_URL` from
> the root `.env`.

---

## 6. Docker memory tuning (8 GB RAM machines)

**Windows only** — create `C:\Users\<you>\.wslconfig`:
```ini
[wsl2]
memory=5GB
processors=4
swap=2GB
```

```powershell
wsl --shutdown
# Restart Docker Desktop from system tray
```

Linux — skip this section.

---

## 7. Check prerequisites

Verifies:
- Docker daemon is running
- Docker Compose is available
- Required ports are free
- `.env` files exist
- Python 3.11.9 is active

**Windows**
```powershell
.\scripts\check-prerequisites.ps1
```

**Linux**
```bash
chmod +x scripts/check-prerequisites.sh
./scripts/check-prerequisites.sh
```

---

## 8. Start infrastructure

Starts:
- PostgreSQL
- Redis
- Kafka
- Zookeeper
- Jaeger
- Prometheus
- Nginx

**Windows**
```powershell
.\scripts\start-infra.ps1
```

**Linux**
```bash
chmod +x scripts/start-infra.sh
./scripts/start-infra.sh
```

---

## 9. Seed the database (first time only)

Run once after infrastructure is up.

Safe to re-run — fully idempotent.

**Windows**
```powershell
.\scripts\seed-db.ps1
```

**Linux**
```bash
chmod +x scripts/seed-db.ps1
./scripts/seed-db.ps1
```

---

## 10. Start application services

Builds and starts:
- API Gateway
- Future agent services

**Windows**
```powershell
.\scripts\run-all-services.ps1
```

**Linux**
```bash
chmod +x scripts/run-all-services.sh
./scripts/run-all-services.sh
```

Gateway docs:
```text
http://localhost:8000/docs
```

---

## 11. Run tests

Run all infrastructure, schema, and gateway tests.

**Windows**
```powershell
.\scripts\test-all.ps1
```

**Linux**
```bash
chmod +x scripts/test-all.sh
./scripts/test-all.sh
```

What it runs:
- Infrastructure integration tests
- Database schema tests
- Gateway async tests inside Docker container

---

## 12. Daily workflow

```powershell
# Verify prerequisites
.\scripts\check-prerequisites.ps1

# Start infra
.\scripts\start-infra.ps1

# Start services
.\scripts\run-all-services.ps1

# Run tests
.\scripts\test-all.ps1

# Stop everything
.\scripts\stop-all.ps1
```