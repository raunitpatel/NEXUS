"""
Search Agent service configuration via pydantic-settings.

All environment variables for the search agent are declared here.
No other file in this service may call os.getenv directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Search Agent settings loaded from environment variables.

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
    service_name: str = "search-agent"

    # Server
    search_agent_host: str = "0.0.0.0"
    search_agent_port: int = 8002

    # Redis (LLM response cache)
    redis_url: str = "redis://:redis_secret@redis:6379/0"
    llm_cache_ttl_seconds: int = 3600

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_events: str = "nexus.events"

    # LLM Provider selection: "claude" | "gemini" | "ollama"
    llm_provider: str = "claude"

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

    # Search tool (stub in AGNT-010, real API in AGNT-024)
    search_provider: str = "mock"
    tavily_api_key: str = "placeholder"
    search_max_results: int = 5

    # Observability
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"


settings = Settings()