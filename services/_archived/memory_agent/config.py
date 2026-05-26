"""
Memory Agent service configuration via pydantic-settings.

All environment variables for the memory agent are declared here.
No other file in this service may call os.getenv directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Memory Agent settings loaded from environment variables.

    All fields default to values suitable for local Docker Compose development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    environment: str = "development"
    log_level: str = "info"
    service_name: str = "memory-agent"

    # Server
    memory_agent_host: str = "0.0.0.0"
    memory_agent_port: int = 8004

    # PostgreSQL + pgvector
    database_url: str = "postgresql+asyncpg://nexus:nexus_secret@postgres:5432/nexus_db"

    # Embedding model (no Claude — local sentence-transformers)
    embedding_model_name: str = "all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    # pgvector similarity search
    vector_similarity_threshold: float = 0.75
    vector_top_k: int = 10

    # Redis (search result cache)
    redis_url: str = "redis://:nexus_secret@redis:6379/0"
    vector_cache_ttl_seconds: int = 300  # 5 minutes

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_tasks: str = "nexus.tasks"
    kafka_topic_events: str = "nexus.events"
    kafka_consumer_group_memory: str = "nexus-memory-agent"

    # Observability
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"


settings = Settings()
