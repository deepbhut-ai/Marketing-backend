"""Pydantic schemas for the brand app (BrandProfile)."""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class BrandProfileCreate(BaseModel):
    brand_name: str = Field("", max_length=255)
    industry: str = Field("", max_length=255)
    website_url: str = Field("", max_length=500)
    tone: str = Field("", max_length=255)
    target_audience: str = Field("", max_length=500)
    brand_summary: str = ""
    brand_keywords: list[str] = Field(default_factory=list)
    primary_colors: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    logo_asset_id: int | None = None
    hashtag_pool: list[str] = Field(default_factory=list)
    bio: str = ""


class BrandProfileUpdate(BaseModel):
    brand_name: str | None = Field(None, max_length=255)
    industry: str | None = Field(None, max_length=255)
    website_url: str | None = Field(None, max_length=500)
    tone: str | None = Field(None, max_length=255)
    target_audience: str | None = Field(None, max_length=500)
    brand_summary: str | None = None
    brand_keywords: list[str] | None = None
    primary_colors: list[str] | None = None
    fonts: list[str] | None = None
    logo_asset_id: int | None = None
    hashtag_pool: list[str] | None = None
    bio: str | None = None


class BrandProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    brand_name: str
    industry: str
    website_url: str
    tone: str
    target_audience: str
    brand_summary: str
    brand_keywords: list[str]
    primary_colors: list[str]
    fonts: list[str]
    logo_asset_id: int | None
    hashtag_pool: list[str]
    bio: str
    created_at: datetime
    updated_at: datetime