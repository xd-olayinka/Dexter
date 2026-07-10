from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:32b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_fast_model: str = "llama3.2:3b"

    # Database
    database_url: str = "postgresql://dexter:dexter@localhost:5432/dexter"

    # Voice
    whisper_model: str = "base"
    piper_voice_orch: str = "en_US-lessac-medium"
    piper_voice_shadow: str = "en_US-alan-medium"

    # Tools
    searxng_url: str = "http://localhost:8888"

    # Notifications
    ntfy_topic: str = "dexter-gates"
    ntfy_server: str = "https://ntfy.sh"

    # Cloud APIs (Phase 5)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""

    # Budget
    daily_cloud_budget: float = 5.00
    per_task_budget_default: float = 0.50

    model_config = {"env_file": ".env", "env_prefix": "DEXTER_"}


settings = Settings()
