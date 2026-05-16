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

## 7. Start infrastructure

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

## 8. Seed the database

Run once after infrastructure is up. Safe to re-run — fully idempotent.

**Windows**
```powershell
.\scripts\seed-db.ps1
```

**Linux**
```bash
python -m pip install -r db/requirements.txt
DATABASE_URL_LOCAL=postgresql+asyncpg://nexus:nexus_1234@localhost:5434/nexus_db \
  python db/seed.py
```

### Verify seed data

```powershell
# Users — expect 10
docker compose exec postgres psql -U nexus -d nexus_db -c "SELECT COUNT(*) FROM users;"

# Agents — expect 4 rows, one per type
docker compose exec postgres psql -U nexus -d nexus_db -c "SELECT type, COUNT(*) FROM agents GROUP BY type ORDER BY type;"

# Runs — expect completed=30, failed=10, pending=10
docker compose exec postgres psql -U nexus -d nexus_db -c "SELECT status, COUNT(*) FROM runs GROUP BY status ORDER BY status;"

# Tasks — expect 200
docker compose exec postgres psql -U nexus -d nexus_db -c "SELECT COUNT(*) FROM tasks;"
```

---

## 9. Verify infrastructure

```bash
# All 4 stateful containers must show healthy
docker compose ps

# Redis
docker compose exec redis redis-cli -a <your_redis_password> PING
# Expected: PONG

# Kafka topics
docker compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list
# Expected: nexus.tasks  nexus.results  nexus.events

# Integration tests
python -m pytest tests/integration/test_infra.py -v
# Expected: 7 passed
```

---

## 10. Daily workflow

```bash
# cd into nexus — pyenv switches to 3.11.9 automatically
cd nexus
python --version   # 3.11.9

# Start infra
.\scripts\start-infra.ps1   # Windows
./scripts/start-infra.sh    # Linux

# Run the service you are working on today
cd services/gateway
python -m uvicorn main:app --reload --port 8000

# Stop at end of day
.\scripts\stop-all.ps1      # Windows
docker compose down          # Linux
```