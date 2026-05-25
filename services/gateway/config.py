"""Gateway service configuration via pydantic-settings.

All environment variables for the gateway service are declared here.
No other file in this service may call os.getenv directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Gateway service settings loaded from environment variables.
    All fields have defaults suitable for local Docker Compose development.
    In production (Railway), these are injected as Railway environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    environment: str = "development"
    log_level: str = "info"
    service_name: str = "gateway"

    # Database

    database_url: str = "postgresql+asyncpg://postgres@db:5432/postgres"
    db_pool_size: int = 10
    db_pool_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_secret_key: str = "change-this-in-production-must-be-32-chars-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_seconds: int = 86400

    # CORS (comma-separated origins)
    cors_origins: str = "http://localhost:3000"

    # Rate limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10

    # Internal service URLs
    orchestrator_url: str = "http://nexus-orchestrator:8001"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
