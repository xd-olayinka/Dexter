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

    # DeepSeek — primary intelligence layer when Ollama isn't running
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    # auto = Ollama if healthy, else DeepSeek if key set, else stub
    primary_provider: str = "auto"  # auto | ollama | deepseek

    # Budget
    daily_cloud_budget: float = 5.00
    per_task_budget_default: float = 0.50

    # Phase 4 · Auth (docs/PHASE_3_4_PLAN.md §1) — off by default so the single-user
    # setup you already have keeps working with no login screen. Turn on once there's
    # an actual team; every request is attributed to an auto-created default business/
    # user until then, same bootstrap-on-first-use pattern as Prometheus's workspace.
    require_auth: bool = False
    session_ttl_days: int = 30

    # Phase 3 · Prometheus MCP bridge (docs/PROMETHEUS_MCP_SPEC.md)
    prometheus_mcp_token: str = ""
    prometheus_mcp_url: str = ""  # e.g. https://your-deployment.convex.site/mcp — empty = not connected

    model_config = {"env_file": ".env", "env_prefix": "DEXTER_"}


settings = Settings()
