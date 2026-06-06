from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")

# asyncpg expects postgresql://
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql+asyncpg://",
        "postgresql://",
        1,
    )


AGENT_DEFINITIONS = [
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


async def seed_agents() -> None:
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        rows = [
            (
                agent["id"],
                agent["name"],
                agent["type"],
                agent["base_url"],
                agent["description"],
            )
            for agent in AGENT_DEFINITIONS
        ]

        await conn.executemany(
            """
            INSERT INTO agents (
                id,
                name,
                type,
                base_url,
                description
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id)
            DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                base_url = EXCLUDED.base_url,
                description = EXCLUDED.description
            """,
            rows,
        )

        count = await conn.fetchval(
            "SELECT COUNT(*) FROM agents"
        )

        print(f"Successfully seeded agents. Total agents: {count}")

    finally:
        await conn.close()


async def main() -> None:
    await seed_agents()


if __name__ == "__main__":
    asyncio.run(main())