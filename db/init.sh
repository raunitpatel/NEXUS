#!/bin/bash
# nexus/db/init.sh
# PostgreSQL initialization script.
# Mounted at: /docker-entrypoint-initdb.d/init.sh
# Runs once on first container boot (when postgres_data volume is empty).
#
# WINDOWS NOTE: This file MUST have LF line endings (enforced by .gitattributes).

set -e

echo "Enabling pgvector extension..."
psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOSQL

echo "Extensions enabled: pgvector, pg_trgm, uuid-ossp"