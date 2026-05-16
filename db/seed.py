"""
db/seed.py

Level 1 seed script for NEXUS.

Bulk-inserts faker-generated data into PostgreSQL:
  - 10 users (bcrypt-hashed passwords)
  - 4 agent definitions (search, code, memory, tool)
  - 50 runs (30 completed, 10 failed, 10 pending)
  - 200 tasks linked proportionally to runs

All inserts use ON CONFLICT DO NOTHING with DETERMINISTIC UUIDs — fully
idempotent. Running the script twice produces identical row counts.

Usage:
    DATABASE_URL_LOCAL=postgresql+asyncpg://nexus:nexus_1234@localhost:5434/nexus_db \
    python db/seed.py
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
import bcrypt
from faker import Faker
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SeedConfig(BaseSettings):
    """Loads seed configuration from db/.env.

    Uses DATABASE_URL_LOCAL for connections from the Windows host (outside
    Docker). asyncpg requires the plain postgresql:// scheme — the
    postgresql+asyncpg:// SQLAlchemy prefix is stripped automatically.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url_local: str = Field(..., alias="DATABASE_URL_LOCAL")
    seed_random_state: int = 42

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def asyncpg_dsn(self) -> str:
        """Return a DSN safe for asyncpg.connect() — strips SQLAlchemy prefix.

        Returns:
            DSN string starting with postgresql://.
        """
        dsn = self.database_url_local
        # Strip SQLAlchemy dialect prefix if present
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        return dsn


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BCRYPT_ROUNDS: int = 12

# Deterministic seed-state — every run generates the same UUIDs
# because Faker and random.Random are seeded with SEED_RANDOM_STATE
SEED_RANDOM_STATE: int = 42

AGENT_DEFINITIONS: list[dict[str, str]] = [
    {
        "id": str(uuid.UUID("00000000-0000-0000-0000-000000000001")),
        "name": "Search Agent",
        "type": "search",
        "description": "Formulates queries, retrieves web results, summarises sources.",
        "base_url": "http://search-agent:8002",
    },
    {
        "id": str(uuid.UUID("00000000-0000-0000-0000-000000000002")),
        "name": "Code Agent",
        "type": "code",
        "description": "Writes, debugs, and executes Python code in a sandboxed subprocess.",
        "base_url": "http://code-agent:8003",
    },
    {
        "id": str(uuid.UUID("00000000-0000-0000-0000-000000000003")),
        "name": "Memory Agent",
        "type": "memory",
        "description": "Stores and retrieves context via pgvector semantic search.",
        "base_url": "http://memory-agent:8004",
    },
    {
        "id": str(uuid.UUID("00000000-0000-0000-0000-000000000004")),
        "name": "Tool Agent",
        "type": "tool",
        "description": "Dispatches function calls to calculator, weather, and wikipedia tools.",
        "base_url": "http://tool-agent:8005",
    },
]

# Schema constraint: status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
RUN_STATUS_DISTRIBUTION: list[str] = (
    ["completed"] * 30 + ["failed"] * 10 + ["pending"] * 10
)

# Schema constraint: status IN ('pending', 'running', 'completed', 'failed', 'retrying')
TASK_STATUSES: list[str] = ["completed", "failed", "pending", "running"]

# Schema constraint: type IN ('search', 'code', 'memory_read', 'memory_write', 'tool', 'synthesize')
TASK_TYPES: list[str] = ["search", "code", "memory_read", "memory_write", "tool", "synthesize"]

LATENCY_MEAN_MS: float = 3000.0
LATENCY_STDDEV_MS: float = 1500.0
LATENCY_MIN_MS: int = 500
LATENCY_MAX_MS: int = 8000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deterministic_uuid(rng: random.Random) -> str:
    """Generate a UUID from a seeded RNG — identical across runs.

    Using rng.getrandbits(128) instead of uuid.uuid4() (which uses os.urandom)
    ensures the same sequence of IDs is produced every time the script runs
    with the same SEED_RANDOM_STATE, making ON CONFLICT DO NOTHING effective.

    Args:
        rng: Seeded Random instance.

    Returns:
        UUID string.
    """
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def _gaussian_latency(rng: random.Random) -> int:
    """Return a Gaussian-distributed latency_ms clamped to [500, 8000].

    Args:
        rng: Seeded Random instance for reproducibility.

    Returns:
        Integer milliseconds between LATENCY_MIN_MS and LATENCY_MAX_MS.
    """
    raw = rng.gauss(LATENCY_MEAN_MS, LATENCY_STDDEV_MS)
    return int(max(LATENCY_MIN_MS, min(LATENCY_MAX_MS, raw)))


def _now() -> datetime:
    """Return current UTC datetime.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Seeders
# ---------------------------------------------------------------------------

async def seed_users(
    conn: asyncpg.Connection,
    fake: Faker,
    rng: random.Random,
    count: int = 10,
) -> int:
    """Bulk-insert faker-generated users with bcrypt-hashed passwords.

    User IDs are deterministic (seeded RNG) so ON CONFLICT DO NOTHING on (id)
    fires correctly on re-runs. Emails are also stable across runs.

    Args:
        conn: Active asyncpg connection.
        fake: Faker instance (pre-seeded for reproducibility).
        rng: Seeded Random instance for deterministic UUIDs.
        count: Number of users to generate (default 10).

    Returns:
        Final COUNT(*) from the users table.
    """
    rows: list[tuple[Any, ...]] = []
    for i in range(count):
        user_id = _deterministic_uuid(rng)
        email = f"user{i+1:02d}@nexus.dev"
        display_name = f"Nexus User {i+1:02d}"
        password = f"Pass{i+1}!"
        hashed_pw = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
        ).decode("utf-8")
        rows.append((user_id, email, hashed_pw, display_name))

    await conn.executemany(
        """
        INSERT INTO users (id, email, password_hash, display_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )
    return await conn.fetchval("SELECT COUNT(*) FROM users")


async def seed_agents(conn: asyncpg.Connection) -> int:
    """Bulk-insert the 4 canonical NEXUS agent definitions.

    Agent IDs are hardcoded deterministic UUIDs — identical every run.
    ON CONFLICT DO NOTHING on (id) makes this fully idempotent.

    Args:
        conn: Active asyncpg connection.

    Returns:
        Final COUNT(*) from the agents table.
    """
    rows: list[tuple[Any, ...]] = [
        (
            a["id"],
            a["name"],
            a["type"],
            a["base_url"],
            a["description"],
        )
        for a in AGENT_DEFINITIONS
    ]

    await conn.executemany(
        """
        INSERT INTO agents (id, name, type, base_url, description)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )
    return await conn.fetchval("SELECT COUNT(*) FROM agents")


async def seed_runs(
    conn: asyncpg.Connection,
    fake: Faker,
    user_ids: list[str],
    rng: random.Random,
) -> tuple[int, list[str]]:
    """Bulk-insert 50 runs with realistic status distribution.

    Run IDs are deterministic (seeded RNG) — same IDs every run so
    ON CONFLICT DO NOTHING on (id) fires correctly on re-runs.

    Status distribution: 30 completed, 10 failed, 10 pending.
    Completed runs get a completed_at timestamp, output text, and
    latency/token metadata. Failed runs get an error message.

    Args:
        conn: Active asyncpg connection.
        fake: Faker instance for query/output text generation.
        user_ids: List of user IDs to assign runs to.
        rng: Seeded Random instance.

    Returns:
        Tuple of (final COUNT(*) from runs, list of inserted run IDs).
    """
    statuses = RUN_STATUS_DISTRIBUTION.copy()
    rng.shuffle(statuses)

    rows: list[tuple[Any, ...]] = []
    run_ids: list[str] = []

    for status in statuses:
        run_id = _deterministic_uuid(rng)
        run_ids.append(run_id)
        user_id = rng.choice(user_ids)
        query = fake.sentence(nb_words=rng.randint(8, 18))

        metadata: dict[str, Any] = {"source": "seed"}
        output: str | None = None
        error: str | None = None
        completed_at: datetime | None = None

        if status == "completed":
            metadata["latency_ms"] = _gaussian_latency(rng)
            metadata["input_tokens"] = rng.randint(200, 2000)
            metadata["output_tokens"] = rng.randint(100, 1500)
            output = fake.paragraph(nb_sentences=3)
            completed_at = _now()
        elif status == "failed":
            error = fake.sentence(nb_words=8)
            completed_at = _now()

        rows.append((
            run_id,
            user_id,
            query,
            status,
            output,
            error,
            json.dumps(metadata),
            completed_at,
        ))

    await conn.executemany(
        """
        INSERT INTO runs (id, user_id, query, status, output, error, metadata, completed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )

    final_count: int = await conn.fetchval("SELECT COUNT(*) FROM runs")
    return final_count, run_ids


async def seed_tasks(
    conn: asyncpg.Connection,
    fake: Faker,
    run_ids: list[str],
    rng: random.Random,
    total_tasks: int = 200,
) -> int:
    """Bulk-insert tasks distributed proportionally across runs.

    Task IDs are deterministic (seeded RNG) — same IDs every run so
    ON CONFLICT DO NOTHING on (id) fires correctly on re-runs.
    input/output columns are JSONB per schema.

    Args:
        conn: Active asyncpg connection.
        fake: Faker instance for input content generation.
        run_ids: List of run IDs to distribute tasks across.
        rng: Seeded Random instance.
        total_tasks: Total number of tasks to insert (default 200).

    Returns:
        Final COUNT(*) from the tasks table.
    """
    agent_rows = await conn.fetch("SELECT id FROM agents")
    agent_ids = [str(r["id"]) for r in agent_rows]

    if not agent_ids:
        raise RuntimeError("No agents found — run seed_agents() first.")

    # Guarantee at least 1 task per run, distribute the rest randomly
    task_counts: dict[str, int] = {run_id: 1 for run_id in run_ids}
    remaining = total_tasks - len(run_ids)
    for _ in range(remaining):
        task_counts[rng.choice(run_ids)] += 1

    rows: list[tuple[Any, ...]] = []
    for run_id, count in task_counts.items():
        for _ in range(count):
            task_id = _deterministic_uuid(rng)
            agent_id = rng.choice(agent_ids)
            status = rng.choice(TASK_STATUSES)
            task_type = rng.choice(TASK_TYPES)
            attempt = rng.randint(1, 3)

            task_input: dict[str, Any] = {
                "query": fake.sentence(nb_words=rng.randint(6, 14))
            }
            task_output: dict[str, Any] | None = None
            error: str | None = None
            completed_at: datetime | None = None

            if status == "completed":
                task_output = {
                    "result": fake.paragraph(nb_sentences=2),
                    "tokens_used": rng.randint(50, 800),
                    "duration_ms": rng.randint(200, 3000),
                }
                completed_at = _now()
            elif status == "failed":
                error = f"Error: {fake.sentence(nb_words=6)}"
                completed_at = _now()

            rows.append((
                task_id,
                run_id,
                agent_id,
                task_type,
                status,
                json.dumps(task_input),
                json.dumps(task_output) if task_output is not None else None,
                error,
                attempt,
                completed_at,
            ))

    await conn.executemany(
        """
        INSERT INTO tasks (
            id, run_id, agent_id, type, status,
            input, output, error, attempt, completed_at
        )
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10)
        ON CONFLICT DO NOTHING
        """,
        rows,
    )

    return await conn.fetchval("SELECT COUNT(*) FROM tasks")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

async def verify(conn: asyncpg.Connection) -> None:
    """Print row counts and status distribution to stdout.

    Args:
        conn: Active asyncpg connection.
    """
    user_count: int = await conn.fetchval("SELECT COUNT(*) FROM users")
    agent_count: int = await conn.fetchval("SELECT COUNT(*) FROM agents")
    run_count: int = await conn.fetchval("SELECT COUNT(*) FROM runs")
    task_count: int = await conn.fetchval("SELECT COUNT(*) FROM tasks")

    status_rows = await conn.fetch(
        "SELECT status, COUNT(*) AS cnt FROM runs GROUP BY status ORDER BY status"
    )
    status_dist = ", ".join(f"{r['status']}={r['cnt']}" for r in status_rows)

    avg_latency: float | None = await conn.fetchval(
        "SELECT AVG((metadata->>'latency_ms')::float) FROM runs WHERE status='completed'"
    )

    print(f"[NEXUS Seed] users:   {user_count}")
    print(f"[NEXUS Seed] agents:  {agent_count}")
    print(f"[NEXUS Seed] runs:    {run_count}  ({status_dist})")
    print(f"[NEXUS Seed] tasks:   {task_count}")
    if avg_latency is not None:
        print(f"[NEXUS Seed] avg completed latency: {avg_latency:.0f}ms")
    print("[NEXUS Seed] Done. Idempotent re-run safe.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Orchestrate all seed operations in dependency order.

    Connects to Postgres via DATABASE_URL_LOCAL (host-side port 5434),
    runs each seeder, prints verification summary.
    Exits with code 1 on any failure with a human-readable message.
    """
    try:
        config = SeedConfig()
    except Exception as exc:
        print(f"[NEXUS Seed] Configuration error: {exc}", file=sys.stderr)
        print(
            "[NEXUS Seed] Ensure DATABASE_URL_LOCAL is set in db/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    dsn = config.asyncpg_dsn()

    try:
        conn: asyncpg.Connection = await asyncpg.connect(dsn)
    except asyncpg.InvalidCatalogNameError:
        print(
            "[NEXUS Seed] Database does not exist. "
            "Run: docker compose up postgres -d",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"[NEXUS Seed] Connection failed: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='users')"
        )
        if not exists:
            print(
                "[NEXUS Seed] Table 'users' not found. "
                "Run db/migrations/001_initial.sql first.",
                file=sys.stderr,
            )
            sys.exit(1)

        fake = Faker()
        fake.seed_instance(SEED_RANDOM_STATE)
        rng = random.Random(SEED_RANDOM_STATE)

        await seed_users(conn, fake, rng)
        await seed_agents(conn)

        user_ids: list[str] = [
            str(r["id"]) for r in await conn.fetch("SELECT id FROM users")
        ]
        _, run_ids = await seed_runs(conn, fake, user_ids, rng)
        await seed_tasks(conn, fake, run_ids, rng)

        await verify(conn)

    except asyncpg.UndefinedTableError as exc:
        print(
            f"[NEXUS Seed] Undefined table: {exc}. "
            "Run db/migrations/001_initial.sql first.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"[NEXUS Seed] Unexpected error: {exc}", file=sys.stderr)
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())