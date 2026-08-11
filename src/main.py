"""
FastAPI application entry point — replaces Django's config/asgi.py.

Run with:
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.core.config import settings
from src.routers import (
    accounts_router, posts_router, scheduler_router,
    comments_router, content_plans_router,
    agent_profile_router, agent_router,
    credits_router, assets_router, brand_router,
)
from src.routers.websocket import router as websocket_router
from src.services.post_scheduler_loop import start_scheduler, stop_scheduler
from src.services.celery_runner import start_celery, stop_celery


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"{settings.APP_NAME} starting...")
    # Ensure media dirs exist
    (settings.MEDIA_DIR / "posts").mkdir(parents=True, exist_ok=True)
    (settings.MEDIA_DIR / "content_plans").mkdir(parents=True, exist_ok=True)
    (settings.MEDIA_DIR / "assets").mkdir(parents=True, exist_ok=True)
    # Auto-start Celery worker + beat (single process) if enabled
    start_celery()
    # Start the automatic in-process post scheduler
    start_scheduler()
    yield
    # Shutdown
    await stop_scheduler()
    stop_celery()
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="Social media automation platform — FastAPI rewrite",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────
# In DEBUG mode, allow any localhost/127.0.0.1 origin (any port) plus
# any Pinggy tunnel URL. Production origins come from settings.CORS_ORIGINS.
_cors_regex = (
    r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    if settings.DEBUG else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static media files ───────────────────────────────────────────────
app.mount(
    settings.MEDIA_URL_PREFIX,
    StaticFiles(directory=str(settings.MEDIA_DIR)),
    name="media",
)

# ── Routers ──────────────────────────────────────────────────────────
app.include_router(accounts_router)
app.include_router(posts_router)
app.include_router(scheduler_router)
app.include_router(comments_router)
app.include_router(content_plans_router)
app.include_router(agent_profile_router)
app.include_router(agent_router)
app.include_router(credits_router)
app.include_router(assets_router)
app.include_router(brand_router)
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "framework": "FastAPI",
        "docs": "/docs",
        "websocket": "/ws/agent/?token=...",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}