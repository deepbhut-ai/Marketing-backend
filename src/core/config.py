"""
Central configuration for the FastAPI app.

All settings are read from environment variables (with sensible defaults
for local development). This replaces Django's `settings.py`.
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent.parent  # fastapi_app/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "AutoSocial AI"
    DEBUG: bool = True
    ALLOWED_HOSTS: list[str] = ["*"]

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:root@localhost:5432/zetta_social"
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://postgres:root@localhost:5432/zetta_social"

    # ── Redis ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # ── Celery (same broker as Django) ───────────────────────────────
    CELERY_BROKER_URL: str = "redis://127.0.0.1:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://127.0.0.1:6379/0"
    CELERY_TIMEZONE: str = "Asia/Kolkata"
    # Auto-start Celery worker + beat inside the FastAPI process.
    # When True, you only need to run uvicorn — no separate Celery terminal.
    AUTOSTART_CELERY: bool = True

    # ── JWT ──────────────────────────────────────────────────────────
    # fastapi-jwt-auth reads these automatically, but we expose them here
    # for clarity.
    AUTH_JWT_SECRET_KEY: str = "django-insecure--0kgpz)11o%f4w+1d@tz7u)n5smiz(g)6r0had9nof7%!d-5*f"
    AUTH_JWT_ACCESS_TOKEN_EXPIRES: int = 86400      # 1 day (seconds)
    AUTH_JWT_REFRESH_TOKEN_EXPIRES: int = 2592000   # 30 days (seconds)
    AUTH_JWT_TOKEN_LOCATION: tuple = ("headers",)
    AUTH_JWT_HEADER_NAME: str = "Authorization"
    AUTH_JWT_HEADER_TYPE: str = "Bearer"

    # ── CORS ─────────────────────────────────────────────────────────
    # In DEBUG mode, allow all localhost dev ports. Add your production
    # frontend origin(s) here for production.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "http://127.0.0.1:8000",
        "https://agents.zettalgor.com",
        "https://marketingira.com",
    ]

    # ── Media ────────────────────────────────────────────────────────
    MEDIA_DIR: Path = BASE_DIR / "media"
    MEDIA_URL_PREFIX: str = "/media"
    # Base URL used for building absolute media URLs in API responses.
    # Must match the public-facing URL of the backend (no trailing slash).
    BASE_URL: str = "https://agents.zettalgor.com"
    SITE_BASE_URL: str = "http://127.0.0.1:8036"

    # ── Local Agent auto-start ───────────────────────────────────────
    # When a post is due and no agent is online, the backend can spawn
    # the local agent process automatically. The agent connects back to
    # this server over WebSocket using the stored raw token.
    # Leave this disabled until a real agent project is available and
    # configured via AGENT_PROJECT_ROOT / AGENT_PYTHON.
    AGENT_PROJECT_ROOT: Path = Path("")
    AGENT_PYTHON: Path = Path("")
    AGENT_START_ENABLED: bool = False
    # WebSocket URL the agent should connect to (this server).
    AGENT_WS_URL: str = "ws://127.0.0.1:8036/ws/agent/"
    # Name of the env var the agent reads for its token.
    AGENT_TOKEN_ENV: str = "AGENT_TOKEN"
    # Name of the env var the agent reads for the WS server URL.
    AGENT_WS_URL_ENV: str = "AGENT_WS_URL"
    # Cooldown (seconds) between auto-start attempts for the same user.
    AGENT_START_COOLDOWN_SECONDS: int = 30

    # ── Zettalgor AI ─────────────────────────────────────────────────
    ZETTALGOR_API_URL: str = "https://api.zettalgor.com/v1/chat/completions"
    ZETTALGOR_API_KEY: str = "ze_al_FPY-bLcxsG2gh6uWee6KLP8JXVYk5F759Ubu7FDm25k"
    ZETTALGOR_MODEL: str = "ZAi8"

    # ── Gemini ───────────────────────────────────────────────────────
    AI_KEY_FERNET_KEY: str = ""
    GEMINI_IMAGE_MODEL: str = "gemini-2.5-flash-image"
    GEMINI_VIDEO_MODEL: str = "veo-3.1-generate-preview"
    GEMINI_TEXT_MODEL: str = "gemini-2.5-flash"
    GEMINI_REQUEST_TIMEOUT: int = 60
    GEMINI_VIDEO_POLL_INTERVAL: int = 10
    GEMINI_VIDEO_TIMEOUT: int = 600

    # ── Content plan limits ──────────────────────────────────────────
    CONTENT_PLAN_MAX_REGENS: int = 3
    CONTENT_PLAN_MAX_DURATION_DAYS: int = 30
    CONTENT_PLAN_MIN_DURATION_DAYS: int = 1
    CONTENT_PLAN_SCRAPE_TIMEOUT: int = 10
    CONTENT_PLAN_IMAGE_CONCURRENCY: int = 3


settings = Settings()

# Ensure media dirs exist
(settings.MEDIA_DIR / "posts").mkdir(parents=True, exist_ok=True)
(settings.MEDIA_DIR / "content_plans").mkdir(parents=True, exist_ok=True)