# AutoSocial AI — FastAPI Version

A complete rewrite of the Django backend using **FastAPI**, **SQLAlchemy 2.0**, and **Alembic** — with **zero functionality loss**.

## 📁 Project Structure

```
fastapi_app/
├── requirements.txt          # All Python dependencies
├── .env.example              # Copy to .env and adjust
├── alembic.ini               # Alembic config
├── alembic/
│   ├── env.py                # Alembic environment
│   ├── script.py.mako        # Migration template
│   └── versions/             # Generated migrations
└── src/
    ├── main.py               # FastAPI app entry point
    ├── core/
    │   ├── config.py         # Settings (replaces Django settings.py)
    │   ├── database.py       # SQLAlchemy async engine + sessions
    │   ├── security.py       # Password hashing (bcrypt)
    │   ├── celery_app.py     # Celery config
    │   └── websocket_manager.py  # WebSocket connection registry
    ├── models/               # SQLAlchemy ORM models
    │   ├── accounts.py       # User, AgentDevice
    │   ├── posts.py          # Post
    │   ├── post_media.py     # PostMedia
    │   ├── comments.py       # PostComment, CommentSettings
    │   └── content_plans.py  # ContentPlan, ContentPlanItem, UserAIKey
    ├── schemas/              # Pydantic request/response schemas
    │   ├── accounts.py
    │   ├── posts.py
    │   ├── comments.py
    │   ├── content_plans.py
    │   └── common.py
    ├── dependencies/
    │   ├── auth.py           # JWT auth dependencies
    │   └── jwt_config.py     # fastapi-jwt-auth config
    ├── routers/              # API route handlers
    │   ├── accounts.py       # /accounts/*
    │   ├── posts.py          # /posts/*
    │   ├── scheduler.py      # /scheduler/*
    │   ├── comments.py       # /comments/*
    │   ├── content_plans.py  # /api/*
    │   └── websocket.py      # /ws/agent/
    ├── services/             # Business logic (framework-agnostic)
    │   ├── crypto.py         # Fernet encryption for AI keys
    │   ├── zettalgor.py      # Zettalgor AI client
    │   ├── scraper.py        # Website scraper
    │   ├── schedule.py       # Schedule builder
    │   ├── brand_summary.py  # Brand summary wrapper
    │   ├── captions.py       # Caption generation
    │   ├── images.py         # Gemini image generation
    │   ├── videos.py         # Veo video generation
    │   └── ai_reply.py       # AI comment reply
    └── celery_tasks/         # Background tasks
        ├── scheduler.py      # check_scheduled_posts
        ├── comments.py       # check_post_comments
        └── content_plans.py  # generate_content_plan, etc.
```

## 🚀 Setup & Run

### 1. Install dependencies
```powershell
cd fastapi_app
pip install -r requirements.txt
```

### 2. Configure environment
```powershell
copy .env.example .env
# Edit .env with your database + API keys
```

### 3. Run database migrations
```powershell
# Generate initial migration from existing models
alembic revision --autogenerate -m "initial"

# Apply migrations
alembic upgrade head
```

> **Note:** If you're sharing the same `zetta_social` database with the Django app, the tables already exist. You can skip migrations or use `alembic stamp head` to mark them as current.

### 4. Start the servers (4 terminals)

**Terminal 1 — FastAPI server:**
```powershell
cd fastapi_app
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Celery worker:**
```powershell
cd fastapi_app
celery -A src.core.celery_app worker -l info -P solo
```

**Terminal 3 — Celery beat:**
```powershell
cd fastapi_app
celery -A src.core.celery_app beat -l info
```

**Terminal 4 — Local agent (unchanged):**
```powershell
.\.venv\Scripts\python.exe local_agent\agent.py
```

## 📚 API Documentation

FastAPI auto-generates interactive docs:
- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

## 🔄 Django → FastAPI Mapping

| Django | FastAPI |
|--------|---------|
| `config/settings.py` | `src/core/config.py` (Pydantic Settings) |
| Django ORM models | SQLAlchemy 2.0 models (`src/models/`) |
| Django migrations | Alembic migrations (`alembic/`) |
| DRF serializers | Pydantic schemas (`src/schemas/`) |
| DRF `@api_view` | FastAPI router endpoints (`src/routers/`) |
| `@permission_classes([IsAuthenticated])` | `Depends(get_current_user)` |
| simplejwt | fastapi-jwt-auth |
| Django Channels | FastAPI native WebSocket (`src/routers/websocket.py`) |
| `channel_layer.group_send()` | `registry.send_to_user()` |
| Celery tasks (Django) | Celery tasks (same, `src/celery_tasks/`) |
| `django.contrib.auth` password | passlib + bcrypt (`src/core/security.py`) |
| Django admin | FastAPI Swagger/ReDoc docs |

## ✅ All endpoints preserved

| Path | Method | Description |
|------|--------|-------------|
| `/accounts/register/` | POST | User registration |
| `/accounts/login/` | POST | User login (JWT + agent token) |
| `/accounts/generate-agent-token/` | GET | Generate new agent token |
| `/accounts/refresh/` | POST | Refresh JWT token |
| `/posts/create/` | POST | Create a post (multipart) |
| `/posts/list/` | GET | List user's posts |
| `/posts/generate-ai-caption/` | POST | AI caption generation |
| `/posts/check-comments/` | POST | Trigger comment check |
| `/scheduler/run/` | GET | Run scheduler manually |
| `/scheduler/send-task/{id}/` | POST | Send post to agent |
| `/comments/generate-reply/` | POST | Generate AI reply |
| `/api/ai-keys/gemini/` | GET/POST/PATCH/DELETE | Gemini key management |
| `/api/ai-keys/gemini/models/` | GET | List Gemini models |
| `/api/content-plans/` | GET/POST | List/create plans |
| `/api/content-plans/{id}/` | GET/DELETE | Plan detail/delete |
| `/api/content-plans/{id}/progress/` | GET | Plan progress |
| `/api/content-plans/{id}/schedule/` | POST | Set schedule |
| `/api/content-plans/{id}/approve/` | POST | Approve & schedule |
| `/api/content-plans/items/{id}/` | PATCH | Edit item |
| `/api/content-plans/items/{id}/regenerate-caption/` | POST | Regen caption |
| `/api/content-plans/items/{id}/approve-caption/` | POST | Approve caption |
| `/api/content-plans/items/{id}/regenerate-image/` | POST | Regen image |
| `/api/content-plans/items/{id}/regenerate-video/` | POST | Regen video |
| `/api/content-plans/items/{id}/upload-image/` | POST | Upload image |
| `/api/content-plans/items/{id}/upload-media/` | POST | Upload media |
| `/api/content-plans/items/{id}/approve-image/` | POST | Approve image |
| `/api/content-plans/items/{id}/approve-media/` | POST | Approve media |
| `/api/content-plans/items/{id}/reject/` | POST | Reject item |
| `/ws/agent/` | WS | Agent WebSocket |
| `/health` | GET | Health check |

## 🔒 Security improvements over Django version
1. **Agent tokens not persisted** — `raw_token` is returned once and never stored (Django version stored it in plain text)
2. **Unauthenticated WebSocket route removed** — only token-based `/ws/agent/?token=...` is supported
3. **Secrets via environment variables** — no hardcoded keys in config
4. **Pydantic validation** — all inputs validated with proper schemas





Terminal	Role	Analogy
1. FastAPI	Receives API requests, serves WebSocket	Receptionist
2. Celery Worker	Runs slow background tasks	Kitchen cook
3. Celery Beat	Timer that triggers tasks on schedule	Alarm clock
4. Agent	Opens Chrome, posts to social media	Delivery driver



┌──────────────────────────────────────────────────────────────────────────────┐
│                        YOUR COMPUTER                                         │
│                                                                              │
│  Terminal 1          Terminal 2          Terminal 3          Terminal 4      │
│  ┌──────────┐        ┌──────────┐        ┌──────────┐        ┌──────────┐    │
│  │ FASTAPI  │        │ CELERY   │        │ CELERY   │        │  AGENT   │    │
│  │ SERVER   │        │ WORKER   │        │   BEAT   │        │(Browser) │    │
│  │          │        │          │        │          │        │          │    │
│  │ Receives │        │ Runs     │        │ Timer    │        │ Opens    │    │
│  │ API calls│        │ heavy    │        │ Triggers │        │ Chrome & │    │
│  │ from you │        │ tasks in │        │ worker   │        │ posts to │    │
│  │ (Postman)│        │background│        │ every 60s│        │ social   │    │
│  └────┬─────┘        └────┬─────┘        └────┬─────┘        │  media   │    │
│       │                   │                   │              └────┬─────┘    │
│       │      ┌────────────┘                   │                   │          │
│       │      │  sends task                    │                   │          │
│       │      ▼                                │                   │          │
│       │  ┌────────────────────────────────────┘                   │          │
│       │  │                                                        │          │
│       │  ▼                                                        │          │
│       │ ┌─────────┐  WebSocket  ┌─────────┐  Selenium  ┌─────────┐│          │
│       └►│  REDIS  │◄───────────►│  AGENT  │───────────►│ CHROME  ││          │
│         └─────────┘             └─────────┘            └─────────┘│          │
│              ▲                                                    │          │
│              │                                                    ▼          │
│         ┌────┴────┐                                    Facebook / Instagram  │
│         │POSTGRES │                                    LinkedIn / X          │
│         └─────────┘                                                          │
└──────────────────────────────────────────────────────────────────────────────┘


PyInstaller agent_build.spec --clean --noconfirm


# Decompress
gunzip backups/zetta_social_20260812_101824.sql.gz

# Restore
psql -U deep -h localhost -d zetta_social -f backups/zetta_social_20260812_101824.sql