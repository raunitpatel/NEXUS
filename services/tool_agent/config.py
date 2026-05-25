"""
Tool Agent service configuration via pydantic-settings.

All environment variables for the memory agent are declared here.
No other file in this service may call os.getenv directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Tool Agent settings loaded from environment variables.

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
    service_name: str = "tool-agent"

    # Server
    tool_agent_host: str = "0.0.0.0"
    tool_agent_port: int = 8004

    # Database (for tool_results persistence)
    database_url: str = "postgresql+asyncpg://nexus:changeme@postgres:5432/nexus_db"
    db_pool_size: int = 3
    db_pool_max_overflow: int = 5

    # LLM Provider selection: "claude" | "gemini" | "ollama"
    llm_provider: str = "gemini"

    # Anthropic
    anthropic_api_key: str = "sk-ant-placeholder"
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_timeout_seconds: int = 60

    # Gemini
    gemini_api_key: str = "gemini_placeholder"
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 60

    # Ollama
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3:7b"
    ollama_timeout_seconds: int = 120

    redis_url: str = "redis://:redis_secret@redis:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_events: str = "nexus.events"

    # Observability
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"

    # Tool API base URLs
    weather_api_base_url: str = "https://api.open-meteo.com/v1"
    wikipedia_api_base_url: str = "https://en.wikipedia.org/api/rest_v1"


settings = Settings()
