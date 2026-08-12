"""Pydantic schemas for the posts app."""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class PostCreateRequest(BaseModel):
    """Used when the API receives JSON. For multipart uploads we read form fields directly."""
    caption: str
    platform: str = Field(..., pattern="^(facebook|instagram|linkedin|x)$")
    scheduled_time: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    caption: str
    media: list[str] = []
    platform: str
    scheduled_time: datetime
    status: str
    post_url: str | None = None
    platform_post_id: str | None = None
    error_message: str | None = None


class PostListResponse(BaseModel):
    success: bool
    message: str
    data: list[PostOut]


class PostCreateResponse(BaseModel):
    success: bool
    message: str
    data: dict


class AICaptionRequest(BaseModel):
    topic: str
    platform: str = "instagram"


class AICaptionResponse(BaseModel):
    success: bool
    message: str
    data: dict


class ContentCreateRequest(BaseModel):
    text: str
    platform: str = "instagram"
    content_type: str = "post"
    tone: str = "friendly"
    language: str = "English"


class ContentCreateData(BaseModel):
    caption: str
    hashtags: str
    suggestions: str


class ContentCreateResponse(BaseModel):
    success: bool
    message: str
    data: ContentCreateData


class CheckCommentsRequest(BaseModel):
    post_id: int
    mode: str = "ai"  # ai / manual / predefine
    reply_text: str = ""


class CheckCommentsResponse(BaseModel):
    success: bool
    message: str


# ──────────────────────────────────────────────────────────────────────────
# Create-Post wizard schemas (multi-stage frontend flow)
# ──────────────────────────────────────────────────────────────────────────

# Frontend platform values → backend platform values
PLATFORM_ALIASES = {
    "twitter": "x",
    "tiktok": "tiktok",
    "youtube": "youtube",
}


class EnhanceDescriptionRequest(BaseModel):
    """Stage 1 — AI-enhance the user's free-form description."""
    description: str
    website: str = ""
    title: str = ""


class EnhanceDescriptionData(BaseModel):
    description: str


class GenerateCaptionsRequest(BaseModel):
    """Stage 3 — generate one caption per scheduled day."""
    description: str
    platforms: list[str]
    from_date: str  # ISO string — start of the range (with time)
    to_date: str  # ISO string — end of the range (with time)
    active_days: list[str] = []  # ["Sun","Mon",...]; empty = all days
    timezone: str = "UTC"
    post_types: list[str] = ["content"]
    website: str = ""
    title: str = ""


class DayCaptionItem(BaseModel):
    day: int
    scheduled_at: str
    content: str
    hashtags: str = ""


class GenerateCaptionsData(BaseModel):
    items: list[DayCaptionItem]


class RegenerateCaptionRequest(BaseModel):
    """Stage 3 — regenerate a single day's caption using a prompt."""
    description: str
    platform: str = "instagram"
    prompt: str = ""
    day: int = 0
    scheduled_at: str = ""
    website: str = ""
    title: str = ""
    post_id: int | None = None  # if provided, updates the existing Post row


class RegenerateCaptionData(BaseModel):
    content: str
    hashtags: str = ""


class RegenerateImageRequest(BaseModel):
    """Stage 4 — regenerate a single day's image using a prompt."""
    description: str
    platform: str = "instagram"
    prompt: str = ""
    day: int = 0
    scheduled_at: str = ""
    brand_summary: str = ""
    model: str = ""
    post_id: int | None = None  # if provided, image is attached to this post


class RegenerateImageData(BaseModel):
    image_url: str
    prompt: str = ""


class RegenerateVideoRequest(BaseModel):
    """Stage 4 — regenerate a single day's video using a prompt."""
    description: str
    platform: str = "instagram"
    prompt: str = ""
    day: int = 0
    scheduled_at: str = ""
    brand_summary: str = ""
    model: str = ""
    post_id: int | None = None  # if provided, video is attached to this post


class RegenerateVideoData(BaseModel):
    video_url: str
    prompt: str = ""


class RegenerateDayGroupRequest(BaseModel):
    """Regenerate caption and/or image/video for all posts in a day group."""
    day_group_id: str
    description: str
    platform: str = "instagram"
    prompt: str = ""
    day: int = 0
    scheduled_at: str = ""
    website: str = ""
    title: str = ""
    brand_summary: str = ""
    model: str = ""
    post_types: list[str] = ["content"]


class UpdateDayGroupScheduleRequest(BaseModel):
    """Reschedule all posts in a day group to a new date/time."""
    day_group_id: str
    scheduled_time: str   # ISO datetime string (the new date+time)
    timezone: str = "UTC"  # IANA tz; naive scheduled_time is interpreted in it


# ──────────────────────────────────────────────────────────────────────────
# Stage 5 — final submit (finalize + schedule pending posts)
# ──────────────────────────────────────────────────────────────────────────

class FinalSubmitItem(BaseModel):
    """One day's worth of finalized content, identified by day_group_id."""
    day_group_id: str
    caption: str | None = None        # final edited caption (None = leave as-is)
    media: str | None = None          # final media path (relative) (None = leave as-is)
    media_type: str = "image"         # "image" | "video" — drives which credit is logged


class FinalSubmitRequest(BaseModel):
    """Stage 5 — Submit button payload.

    Each item targets all posts sharing a day_group_id: their caption/media
    are updated and status flipped pending → scheduled.
    """
    items: list[FinalSubmitItem]


# ──────────────────────────────────────────────────────────────────────────
# PostLog — post lifecycle audit log
# ──────────────────────────────────────────────────────────────────────────

class PostLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    post_id: int | None = None
    action: str
    platform: str | None = None
    day_group_id: str | None = None
    meta: dict | None = None
    note: str
    created_at: datetime


class PostLogListOut(BaseModel):
    items: list[PostLogOut]
    total: int
    page: int
    page_size: int