# Create the file with explicit LF line endings
#!/bin/bash
# db/init.sh
# Bootstraps the NEXUS database: installs pgvector extension, then applies schema.sql.
# Executed automatically by PostgreSQL on first container start via docker-entrypoint-initdb.d.
# Idempotent: safe to run multiple times due to IF NOT EXISTS guards throughout schema.sql.

set -e

echo "[NEXUS init.sh] Installing pgvector extension..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "[NEXUS init.sh] Applying schema.sql..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -f /docker-entrypoint-initdb.d/schema.sql

echo "[NEXUS init.sh] Database bootstrap complete."


