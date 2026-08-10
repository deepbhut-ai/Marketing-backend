"""Pydantic schemas for the content_plans app."""
from datetime import datetime, date, time
from pydantic import BaseModel, Field, ConfigDict, HttpUrl


# ── Gemini key ───────────────────────────────────────────────────────

class GeminiKeySave(BaseModel):
    api_key: str


class GeminiKeyOut(BaseModel):
    configured: bool
    last4: str = ""
    validated_at: datetime | None = None
    default_image_model: str = ""
    default_video_model: str = ""


class GeminiModelDefaults(BaseModel):
    default_image_model: str | None = None
    default_video_model: str | None = None


class GeminiModelsOut(BaseModel):
    image_models: list[dict]
    video_models: list[dict]


# ── Content plan ─────────────────────────────────────────────────────

class ContentPlanCreate(BaseModel):
    website_url: str
    duration_days: int = Field(..., ge=1, le=30)
    platforms: list[str] = Field(..., min_length=1)
    frequency: str = "daily"
    custom_interval_days: int = 1
    start_date: date | None = None
    posting_time: time | None = None
    media_type: str = "image"
    image_model: str = ""
    video_model: str = ""


class ContentPlanSchedule(BaseModel):
    frequency: str = "daily"
    custom_interval_days: int = 1
    start_date: date
    posting_time: time


class ContentPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sequence: int
    platform: str
    topic: str
    caption: str
    hashtags: str
    image: str | None = None
    image_prompt: str
    video: str | None = None
    video_prompt: str
    media_type: str
    media_url: str | None = None
    scheduled_time: datetime | None = None
    status: str
    caption_regen_count: int
    image_regen_count: int
    video_regen_count: int
    error_message: str
    created_at: datetime
    updated_at: datetime


class ContentPlanListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_url: str
    duration_days: int
    frequency: str
    custom_interval_days: int
    platforms: list
    start_date: date | None
    posting_time: time | None
    total_posts: int
    media_type: str
    image_model: str
    video_model: str
    status: str
    progress: int
    error_message: str
    created_at: datetime
    updated_at: datetime


class ContentPlanDetailOut(ContentPlanListOut):
    brand_summary: str
    brand_keywords: list
    items: list[ContentPlanItemOut] = []


class ContentPlanProgressOut(BaseModel):
    plan_id: int
    status: str
    progress: int
    completed_items: int
    total_posts: int
    error_message: str


class ContentPlanItemUpdate(BaseModel):
    caption: str | None = None
    hashtags: str | None = None
    scheduled_time: datetime | None = None
    media_type: str | None = None


class RegenerateCaptionRequest(BaseModel):
    topic: str | None = None


class RegenerateMediaRequest(BaseModel):
    prompt_override: str = ""


class ApproveResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None