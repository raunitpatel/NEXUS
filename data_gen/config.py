"""
Configuration for NEXUS Level 2 data generation script.

Loads from data_gen/.env. All settings have sensible defaults for local
Docker Compose development. Never access os.getenv directly anywhere in data_gen/.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulationSettings(BaseSettings):
    """
    Settings for simulate_runs.py loaded from data_gen/.env.

    Attributes:
        gateway_base_url: Base URL of the NEXUS API Gateway.
        sim_user_email: Email address for the simulation user account.
        sim_user_password: Password for the simulation user account.
        sim_user_display_name: Display name shown in Postgres users table.
        database_url_local: asyncpg DSN for direct DB verification queries.
        batch_size: Number of runs to fire concurrently per batch.
        run_timeout_seconds: Max seconds to wait for a single run to complete via SSE.
        max_concurrent_runs: Semaphore limit for concurrent SSE subscriptions.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gateway_base_url: str = "http://localhost:8000"
    sim_user_email: str = "sim@nexus.dev"
    sim_user_password: str = "SimPass123!"
    sim_user_display_name: str = "Simulation User"
    database_url_local: str = "postgresql://nexus:nexus_secret@localhost:5434/nexus_db"
    batch_size: int = 5
    run_timeout_seconds: int = 120
    max_concurrent_runs: int = 5

    def asyncpg_dsn(self) -> str:
        """
        Return a DSN safe for asyncpg.connect() — strips SQLAlchemy prefix.

        Returns:
            DSN string starting with postgresql://.
        """
        dsn = self.database_url_local
        if dsn.startswith("postgresql+asyncpg://"):
            return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        if dsn.startswith("postgres://"):
            return dsn.replace("postgres://", "postgresql://", 1)
        return dsn


settings = SimulationSettings()