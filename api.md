# Marketing Backend API Documentation

**Base URL:** `http://127.0.0.1:8036` (local) · `https://agents.zettalgor.com` (production)

**Auth:** All protected endpoints require `Authorization: Bearer <access_token>` header.
Get the token via `POST /accounts/login/`.

**Response format:** All endpoints return `{ "success": bool, "message": str, "data": ... }`.

---

## Table of Contents

1. [Health](#1-health)
2. [Accounts (Auth)](#2-accounts-auth)
3. [Posts](#3-posts)
4. [Create-Post Wizard (new)](#4-create-post-wizard)
5. [Content Plans](#5-content-plans)
6. [Scheduler](#6-scheduler)
7. [Comments](#7-comments)
8. [Agent Profile](#8-agent-profile)
9. [WebSocket](#9-websocket)

---

## 1. Health

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | ❌ | App metadata (name, version, docs URL) |
| GET | `/health` | ❌ | Health check → `{"status":"ok"}` |

---

## 2. Accounts (Auth)

Prefix: `/accounts`

### Register
```
POST /accounts/register/
```
```json
{
  "username": "string",
  "email": "user@example.com",
  "password": "string (min 6 chars)"
}
```

### Login
```
POST /accounts/login/
```
```json
{
  "email": "user@example.com",
  "password": "string",
  "device_name": "My Device"
}
```
**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": 10,
    "access": "JWT_ACCESS_TOKEN",
    "refresh": "JWT_REFRESH_TOKEN",
    "device_id": 5,
    "agent_token": "RAW_AGENT_TOKEN",
    "type": "user"
  }
}
```

### Refresh Token
```
POST /accounts/refresh/
```
```json
{ "refresh": "JWT_REFRESH_TOKEN" }
```

### Generate Agent Token
```
GET /accounts/generate-agent-token/?device_name=My+Device
Authorization: Bearer <access_token>
```

---

## 3. Posts

Prefix: `/posts`



### List Posts
```
GET /posts/list/
Authorization: Bearer <token>
```


### Generate Image (single)
```
POST /posts/generate-image/
Authorization: Bearer <token>
```
```json
{
  "text": "string",
  "platform": "instagram",
  "brand_summary": "",
  "model": "",
  "prompt_override": ""
}
```
> Requires a saved Gemini API key (`POST /api/ai-keys/gemini/`).

### Check Comments
```
POST /posts/check-comments/
Authorization: Bearer <token>
```
```json
{
  "post_id": 200,
  "mode": "ai",
  "reply_text": ""
}
```

---

## 4. Create-Post Wizard

These are the new endpoints built for the `/create-post` frontend page (5-stage wizard).

Prefix: `/posts`

### Stage 1 — Enhance Description
```
POST /posts/enhance-description/
Authorization: Bearer <token>
```
```json
{
  "description": "We build custom AI models for businesses",
  "website": "https://zettalgor.com",
  "title": "AI Outreach Campaign"
}
```
**Response:**
```json
{
  "success": true,
  "message": "Description enhanced",
  "data": { "description": "Enhanced description text..." }
}
```

### Stage 3 — Generate Captions (creates Post rows)
```
POST /posts/generate-captions/
Authorization: Bearer <token>
```
```json
{
  "description": "We build custom AI models for businesses",
  "platforms": ["instagram", "facebook", "linkedin"],
  "from_date": "2026-08-06T10:00:00",
  "to_date": "2026-08-12T18:00:00",
  "active_days": ["Mon", "Wed", "Fri"],
  "timezone": "Asia/Kolkata",
  "post_types": ["content"],
  "website": "https://zettalgor.com",
  "title": "AI Outreach Campaign"
}
```
**Response:**
```json
{
  "success": true,
  "message": "9 post(s) created with AI captions",
  "data": {
    "items": [
      {
        "day": 0,
        "scheduled_at": "2026-08-06T10:00:00+05:30",
        "content": "Caption text...",
        "hashtags": "#AI #Outreach",
        "day_group_id": "481dd964-7f8d-4b8a-b0fe-e6eccf4bd3fd",
        "post_ids": [200, 201, 202]
      }
    ],
    "posts": [
      {
        "post_id": 200,
        "user_id": 12,
        "day": 0,
        "day_group_id": "481dd964-...",
        "platform": "instagram",
        "caption": "Caption text...\n\n#AI #Outreach",
        "scheduled_time": "2026-08-06T10:00:00+05:30",
        "status": "pending"
      }
    ],
    "day_groups": [
      {
        "day": 0,
        "day_group_id": "481dd964-...",
        "scheduled_time": "2026-08-06T10:00:00+05:30",
        "post_ids": [200, 201, 202]
      }
    ],
    "total_posts": 9,
    "total_days": 3
  }
}
```
> Creates one Post per day × platform (status=`pending`). All posts on the same day share a `day_group_id` (UUID).

### Stage 3 — Regenerate Single Day's Caption
```
POST /posts/regenerate-caption/
Authorization: Bearer <token>
```
```json
{
  "description": "We build custom AI models for businesses",
  "platform": "instagram",
  "prompt": "focus on customer testimonials",
  "day": 1,
  "scheduled_at": "2026-08-08T14:00:00",
  "website": "https://zettalgor.com",
  "title": "AI Outreach Campaign",
  "post_id": 203
}
```
> If `post_id` is provided, the existing Post row's caption is updated in the DB.

### Get Posts by Day Group
```
GET /posts/day-group/{day_group_id}/
Authorization: Bearer <token>
```
**Response:**
```json
{
  "success": true,
  "message": "3 post(s) found for this day",
  "data": {
    "day_group_id": "481dd964-...",
    "scheduled_time": "2026-08-06T10:00:00+05:30",
    "total_posts": 3,
    "posts": [
      {
        "post_id": 200,
        "platform": "facebook",
        "caption": "...",
        "media": [],
        "scheduled_time": "...",
        "status": "pending"
      }
    ]
  }
}
```

### Stage 4 — Generate Images (batch)
```
POST /posts/generate-images/
Authorization: Bearer <token>
```
```json
{
  "description": "We build custom AI models for businesses",
  "platforms": ["instagram"],
  "from_date": "2026-08-06T10:00:00",
  "to_date": "2026-08-12T18:00:00",
  "active_days": ["Mon", "Wed", "Fri"],
  "timezone": "Asia/Kolkata",
  "prompts": [],
  "brand_summary": "",
  "model": ""
}
```
> Requires a saved Gemini API key.

### Stage 4 — Regenerate Single Day's Image
```
POST /posts/regenerate-image/
Authorization: Bearer <token>
```
```json
{
  "description": "We build custom AI models for businesses",
  "platform": "instagram",
  "prompt": "bright product shot on purple gradient",
  "day": 1,
  "scheduled_at": "2026-08-08T14:00:00",
  "brand_summary": "",
  "model": ""
}
```

### Stage 5 — Bulk Create / Schedule All Posts
```
POST /posts/bulk-create/
Authorization: Bearer <token>
```
```json
{
  "timezone": "Asia/Kolkata",
  "items": [
    {
      "caption": "Caption text #hashtags",
      "platform": "instagram",
      "scheduled_time": "2026-08-06T10:00:00",
      "image_url": "http://127.0.0.1:8036/media/generated/abc.png",
      "timezone": "Asia/Kolkata"
    }
  ]
}
```
> If `image_url` is provided, the backend downloads it and attaches as `PostMedia`. Posts with past `scheduled_time` are skipped. Status set to `scheduled`.

---

## 5. Content Plans

Prefix: `/api`

### Gemini Key Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ai-keys/gemini/` | Get key status (configured, last4, defaults) |
| POST | `/api/ai-keys/gemini/` | Save/validate Gemini API key `{"api_key":"..."}` |
| PATCH | `/api/ai-keys/gemini/` | Update default image/video models |
| DELETE | `/api/ai-keys/gemini/` | Remove stored key |
| GET | `/api/ai-keys/gemini/models/` | List available Gemini model choices |

### Plans CRUD

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/content-plans/` | List all plans for current user |
| POST | `/api/content-plans/` | Create plan + start async generation |
| GET | `/api/content-plans/{plan_id}/` | Get plan with all items |
| DELETE | `/api/content-plans/{plan_id}/` | Delete plan (if not scheduled) |
| GET | `/api/content-plans/{plan_id}/progress/` | Get generation progress |
| POST | `/api/content-plans/{plan_id}/schedule/` | Set schedule + re-spread items |
| POST | `/api/content-plans/{plan_id}/approve/` | Approve → creates scheduled Post rows |

**Create plan body:**
```json
{
  "website_url": "https://example.com",
  "duration_days": 7,
  "platforms": ["instagram", "facebook"],
  "frequency": "daily",
  "custom_interval_days": 1,
  "start_date": "2026-08-06",
  "posting_time": "10:00:00",
  "media_type": "image",
  "image_model": "",
  "video_model": ""
}
```

### Item Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| PATCH | `/api/content-plans/items/{item_id}/` | Update caption/hashtags/scheduled_time/media_type |
| POST | `/api/content-plans/items/{item_id}/regenerate-caption/` | Regenerate caption via Celery |
| POST | `/api/content-plans/items/{item_id}/approve-caption/` | Approve caption → trigger media gen |
| POST | `/api/content-plans/items/{item_id}/regenerate-image/` | Regenerate image via Celery |
| POST | `/api/content-plans/items/{item_id}/regenerate-video/` | Regenerate video via Celery |
| POST | `/api/content-plans/items/{item_id}/upload-image/` | Upload custom image (multipart) |
| POST | `/api/content-plans/items/{item_id}/upload-media/` | Alias of upload-image |
| POST | `/api/content-plans/items/{item_id}/approve-image/` | Approve media |
| POST | `/api/content-plans/items/{item_id}/approve-media/` | Alias of approve-image |
| POST | `/api/content-plans/items/{item_id}/reject/` | Reject item |

---

## 6. Scheduler

Prefix: `/scheduler`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/scheduler/run/` | Process all due scheduled posts → send to agent via WebSocket |
| POST | `/scheduler/send-task/{post_id}/` | Manually send a specific post to the agent |

---

## 7. Comments

Prefix: `/comments`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/comments/generate-reply/` | Generate AI reply for latest unanswered comment |

**Body:**
```json
{
  "post_id": 200,
  "mode": "AI"
}
```

---

## 8. Agent Profile

Prefix: `/agent-profile`

### JWT-authenticated

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agent-profile/` | Get/auto-create Chrome profile settings |
| POST | `/agent-profile/open-chrome/` | Open Chrome for platform login `{"platforms":["instagram"]}` |
| POST | `/agent-profile/update/` | Update Chrome profile dir `{"user_data_dir":"...","profile_directory":"Default"}` |
| GET | `/agent-profile/system-profiles/` | List all Chrome profiles on machine |
| GET | `/agent-profile/current-chrome-profile/` | Detect current Chrome profile |
| POST | `/agent-profile/import-profile/` | Import Chrome profile `{"profile_name":"Default"}` |

### Agent-token-authenticated (no JWT)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/agent-profile/by-token/?token=...` | Agent token | Get profile by agent token |
| GET | `/agent-profile/system-profiles/by-token/?token=...` | Agent token | List Chrome profiles |
| GET | `/agent-profile/current-chrome-profile/by-token/?token=...` | Agent token | Detect current profile |
| POST | `/agent-profile/import-profile/by-token/` | Agent token | Import profile `{"token":"...","profile_name":"..."}` |

---

## 9. WebSocket

### Agent WebSocket
```
WS /ws/agent/?token=<agent_token>
```
- Authenticates via raw agent token (from login response `agent_token` field)
- On connect, dispatches any due scheduled posts to the agent
- Handles incoming `task_result` messages to update post status

**Message types sent to agent:**
```json
{ "type": "send_task", "post_id": 200, "platform": "instagram", "caption": "...", "media": ["url1"] }
{ "type": "send_check_comments", "post_id": 200, "platform": "instagram", "post_url": "...", "reply_mode": "ai", "reply_text": "" }
```

**Message types received from agent:**
```json
{ "type": "task_result", "post_id": 200, "status": "posted", "post_url": "...", "error": "" }
```

---

## Platform Values

| Frontend value | Backend value | Notes |
|----------------|---------------|-------|
| `facebook` | `facebook` | — |
| `instagram` | `instagram` | — |
| `linkedin` | `linkedin` | — |
| `twitter` | `x` | Auto-mapped via `PLATFORM_ALIASES` |
| `x` | `x` | — |
| `tiktok` | `tiktok` | — |
| `youtube` | `youtube` | — |

## Post Status Flow

```
pending → scheduled → processing → posted
                                    ↘ failed
```

| Status | Meaning |
|--------|---------|
| `pending` | Created but not yet scheduled (Stage 3 output) |
| `scheduled` | Scheduled and waiting for due time (Stage 5 output) |
| `processing` | Sent to agent, being published |
| `posted` | Successfully published |
| `failed` | Publishing failed (see `error_message`) |

---

## Date/Timezone Handling

- `from_date` / `to_date` / `scheduled_time` accept ISO strings with or without timezone
- Naive datetimes are interpreted in the `timezone` field (e.g. `Asia/Kolkata`)
- All times are converted to UTC for database storage
- `active_days` accepts: `["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]` (empty = all days)

## Total Endpoints: 51

| Router | Count |
|--------|-------|
| Health | 2 |
| Accounts | 5 |
| Posts (incl. wizard) | 13 |
| Content Plans | 22 |
| Scheduler | 2 |
| Comments | 1 |
| Agent Profile | 10 |
| WebSocket | 1 |