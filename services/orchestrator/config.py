"""
Orchestrator service configuration via pydantic-settings.

All environment variables for the orchestrator service are declared here.
No other file in this service may call os.getenv directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Orchestrator service settings loaded from environment variables.

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
    service_name: str = "orchestrator"

    # Database
    database_url: str = "postgresql+asyncpg://nexus:nexus_secret@postgres:5432/nexus_db"
    db_pool_size: int = 5
    db_pool_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://:redis_secret@redis:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_tasks: str = "nexus.tasks"
    kafka_topic_results: str = "nexus.results"
    kafka_topic_events: str = "nexus.events"
    kafka_consumer_group_orchestrator: str = "nexus-orchestrator"

    # LLM — Ollama (local, no API key required for portfolio demo)
    # When swapping to Claude post-portfolio, only OllamaProvider instantiation
    # in llm_provider.py changes — nothing else in this service touches these.
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2"

    # Anthropic — reserved for future provider swap, not used in AGNT-007/008
    anthropic_api_key: str = "sk-ant-placeholder"



    # Internal agent URLs
    search_agent_url: str = "http://search-agent:8002"
    code_agent_url: str = "http://code-agent:8003"
    memory_agent_url: str = "http://memory-agent:8004"
    tool_agent_url: str = "http://tool-agent:8005"

    # LangGraph execution
    max_plan_retries: int = 3
    task_timeout_seconds: int = 30
    max_parallel_tasks: int = 4

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: int = 60

    # Observability
    otel_exporter_otlp_endpoint: str = "http://jaeger:4317"

settings = Settings()