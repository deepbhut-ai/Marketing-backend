"""Pydantic schemas for the assets app (Asset)."""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, HttpUrl


class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field("", max_length=2000)
    asset_type: str = Field(..., max_length=20, description="image|video|gif|document|audio|link")
    url: str | None = Field(None, max_length=1024, description="Optional URL (e.g. for AI-generated assets served from a CDN)")
    thumbnail_url: str | None = Field(None, max_length=1024)
    mime_type: str | None = Field(None, max_length=128)
    file_size: int | None = Field(None, ge=0, description="Size in bytes")
    source: str = Field("uploaded", max_length=20, description="uploaded | ai")
    external_id: str | None = Field(None, max_length=255)
    tags: list[str] | None = None
    meta: dict | None = None
    is_favorite: bool = False
    is_archived: bool = False


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    asset_type: str | None = Field(None, max_length=20)
    url: str | None = Field(None, max_length=1024)
    thumbnail_url: str | None = Field(None, max_length=1024)
    mime_type: str | None = Field(None, max_length=128)
    file_size: int | None = Field(None, ge=0)
    source: str | None = Field(None, max_length=20)
    external_id: str | None = Field(None, max_length=255)
    tags: list[str] | None = None
    meta: dict | None = None
    is_favorite: bool | None = None
    is_archived: bool | None = None


class AssetOut(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    file: str | None = None
    # Absolute public URL (derived from file or url).
    public_url: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetListOut(BaseModel):
    items: list[AssetOut]
    total: int
    page: int
    page_size: int


class AssetSummary(BaseModel):
    total: int
    by_type: dict[str, int]
    favorites: int
    archived: int
