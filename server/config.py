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
    piper_voice_shadow: str = "en_GB-alan-medium"

    # Tools
    searxng_url: str = "http://localhost:8888"

    # Notifications
    ntfy_topic: str = "dexter-gates"
    ntfy_server: str = "https://ntfy.sh"

    # Cloud APIs (Phase 5)
    anthropic_api_key: str = ""
    # Opus-tier model the Selector uses for the hardest tasks; Sonnet 5 / Haiku 4.5 cover the
    # cheaper tiers, Fable 5.1 is opt-in (DEXTER_SELECTOR_ALLOW_FABLE) since it costs 2x Opus.
    anthropic_model: str = "claude-opus-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    # $/1M tokens for openai_model when it isn't in the built-in price table
    openai_price_in: float | None = None
    openai_price_out: float | None = None
    selector_allow_fable: bool = False
    # re-run tasks that were queued/running/gated when the server stopped
    resume_interrupted: bool = True
    # Home "hours reclaimed" default when a task has no minutes_saved of its own
    default_minutes_saved: int = 15
    groq_api_key: str = ""

    # DeepSeek — primary intelligence layer when Ollama isn't running
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    # auto = Ollama if healthy, else DeepSeek if key set, else stub
    primary_provider: str = "auto"  # auto | ollama | deepseek

    # Budget
    daily_cloud_budget: float = 5.00
    monthly_budget: float = 100.00
    per_task_budget_default: float = 0.50

    # Phase 4 · Auth (docs/PHASE_3_4_PLAN.md §1) — off by default so the single-user
    # setup you already have keeps working with no login screen. Turn on once there's
    # an actual team; every request is attributed to an auto-created default business/
    # user until then, same bootstrap-on-first-use pattern as Prometheus's workspace.
    require_auth: bool = False
    session_ttl_days: int = 30
    # Who may create a NEW account (and business) at /api/auth/register. Claiming an invite
    # always works. open = anyone · first = only while no account exists yet (the owner),
    # then invite-only · invite = never. Hosted deploys should not be open: every business
    # spends the same model keys.
    signup_mode: str = "open"
    # Seconds between Anthony's sweeps for Prometheus gate checks addressed to it (gate_voter.py); 0 = off.
    gate_vote_interval: int = 120
    # Directory holding the built frontend (the combined Railway image); empty = API only.
    static_dir: str = ""

    # Phase 3 · Prometheus MCP bridge (docs/PROMETHEUS_MCP_SPEC.md)
    prometheus_mcp_token: str = ""
    prometheus_mcp_url: str = ""  # e.g. https://your-deployment.convex.site/mcp — empty = not connected

    model_config = {"env_file": ".env", "env_prefix": "DEXTER_"}


settings = Settings()
