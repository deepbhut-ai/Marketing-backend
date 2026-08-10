"""Pydantic schemas for the credits app (CreditRate + CreditLog)."""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ── CreditRate ───────────────────────────────────────────────────────

class CreditRateBase(BaseModel):
    action_key: str = Field(..., max_length=64, description="Unique key, e.g. image_generation")
    label: str = Field("", max_length=120)
    credits: int = Field(1, ge=0, description="Cost per use")
    is_active: bool = True


class CreditRateCreate(CreditRateBase):
    pass


class CreditRateUpdate(BaseModel):
    label: str | None = Field(None, max_length=120)
    credits: int | None = Field(None, ge=0)
    is_active: bool | None = None


class CreditRateOut(CreditRateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ── CreditLog ────────────────────────────────────────────────────────

class CreditLogCreate(BaseModel):
    """The caller only sends the action_key + optional reference.

    `credits_used` is looked up from the CreditRate table by the router,
    NOT passed by the caller.
    """
    action_key: str = Field(..., max_length=64)
    reference_type: str | None = Field(None, max_length=64)
    reference_id: int | None = None
    meta: dict | None = None
    note: str = ""


class CreditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action_key: str
    credits_used: int
    reference_type: str | None = None
    reference_id: int | None = None
    meta: dict | None = None
    note: str
    created_at: datetime


class CreditLogListOut(BaseModel):
    items: list[CreditLogOut]
    total: int
    page: int
    page_size: int


# ── Usage summary ────────────────────────────────────────────────────

class CreditUsageSummary(BaseModel):
    """Aggregate usage for the current user."""
    total_used: int
    by_action: dict[str, int]
