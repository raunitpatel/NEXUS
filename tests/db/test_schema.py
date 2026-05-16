# db/tests/test_schema.py
"""
Integration tests for NEXUS PostgreSQL schema (AGNT-003).

Requires:
    docker compose up -d postgres

Run:
    python -m pytest tests/db/test_schema.py -v
"""

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL_LOCAL",
    "postgresql://nexus:nexus_secret@localhost:5434/nexus_db",
)

ASYNCPG_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

@pytest_asyncio.fixture()
async def conn() -> asyncpg.Connection:
    """Create asyncpg connection per test."""
    connection = await asyncpg.connect(ASYNCPG_URL)
    yield connection
    await connection.close()


@pytest.mark.asyncio
async def test_all_seven_tables_exist(conn: asyncpg.Connection) -> None:
    """Verify all required tables exist."""
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
        """
    )

    table_names = {row["tablename"] for row in rows}

    expected = {
        "users",
        "agents",
        "runs",
        "tasks",
        "events",
        "tool_results",
        "embeddings_metadata",
    }

    assert expected.issubset(table_names), (
        f"Missing tables: {expected - table_names}"
    )


@pytest.mark.asyncio
async def test_pgvector_extension_installed(
    conn: asyncpg.Connection,
) -> None:
    """Verify pgvector extension is installed."""
    row = await conn.fetchrow(
        """
        SELECT extname
        FROM pg_extension
        WHERE extname = 'vector';
        """
    )

    assert row is not None, "pgvector extension not installed"


@pytest.mark.asyncio
async def test_ivfflat_index_exists(
    conn: asyncpg.Connection,
) -> None:
    """Verify IVFFLAT index exists on embeddings."""
    row = await conn.fetchrow(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'embeddings_metadata'
          AND indexname = 'idx_embeddings_embedding';
        """
    )

    assert row is not None, (
        "IVFFLAT index idx_embeddings_embedding not found"
    )

    assert "ivfflat" in row["indexdef"].lower(), (
        f"Index is not IVFFLAT: {row['indexdef']}"
    )

    assert "vector_cosine_ops" in row["indexdef"], (
        f"Wrong operator class: {row['indexdef']}"
    )


@pytest.mark.asyncio
async def test_runs_fk_to_users(
    conn: asyncpg.Connection,
) -> None:
    """Verify runs.user_id FK references users.id with CASCADE delete."""
    row = await conn.fetchrow(
        """
        SELECT
            tc.constraint_name,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        WHERE tc.table_name = 'runs'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND rc.unique_constraint_name IN (
              SELECT constraint_name
              FROM information_schema.table_constraints
              WHERE table_name = 'users'
                AND constraint_type = 'PRIMARY KEY'
          );
        """
    )

    assert row is not None, "FK from runs to users not found"

    assert row["delete_rule"] == "CASCADE", (
        f"Expected CASCADE, got: {row['delete_rule']}"
    )


@pytest.mark.asyncio
async def test_runs_composite_index_exists(
    conn: asyncpg.Connection,
) -> None:
    """Verify composite index exists on runs(user_id, created_at DESC)."""
    row = await conn.fetchrow(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'runs'
          AND indexname = 'idx_runs_user_id_created_at';
        """
    )

    assert row is not None, (
        "Composite index idx_runs_user_id_created_at not found"
    )


@pytest.mark.asyncio
async def test_schema_idempotency(
    conn: asyncpg.Connection,
) -> None:
    """Verify CREATE TABLE IF NOT EXISTS is idempotent."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


@pytest.mark.asyncio
async def test_embedding_dimension_constraint(
    conn: asyncpg.Connection,
) -> None:
    """Verify pgvector rejects non-384-dimension vectors."""
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()

    await conn.execute(
        """
        INSERT INTO users (id, email, password_hash)
        VALUES ($1, $2, $3)
        """,
        user_id,
        f"test_{str(user_id)[:8]}@nexus.dev",
        "hashed_password",
    )

    await conn.execute(
        """
        INSERT INTO runs (id, user_id, query)
        VALUES ($1, $2, $3)
        """,
        run_id,
        user_id,
        "test query",
    )

    wrong_dim_vector = "[" + ",".join(["0.1"] * 383) + "]"

    with pytest.raises(asyncpg.exceptions.DataError):
        await conn.execute(
            """
            INSERT INTO embeddings_metadata (run_id, content, embedding)
            VALUES ($1, $2, $3::vector)
            """,
            run_id,
            "test content",
            wrong_dim_vector,
        )

    await conn.execute("DELETE FROM runs WHERE id = $1", run_id)
    await conn.execute("DELETE FROM users WHERE id = $1", user_id)


@pytest.mark.asyncio
async def test_updated_at_trigger_exists(
    conn: asyncpg.Connection,
) -> None:
    """Verify updated_at triggers exist on users, runs, and tasks."""
    rows = await conn.fetch(
        """
        SELECT trigger_name
        FROM information_schema.triggers
        WHERE trigger_name IN (
            'trg_users_updated_at',
            'trg_runs_updated_at',
            'trg_tasks_updated_at'
        );
        """
    )

    trigger_names = {row["trigger_name"] for row in rows}

    expected = {
        "trg_users_updated_at",
        "trg_runs_updated_at",
        "trg_tasks_updated_at",
    }

    assert expected.issubset(trigger_names), (
        f"Missing triggers: {expected - trigger_names}"
    )