"""Pydantic schemas for the comments app."""
from pydantic import BaseModel


class GenerateReplyRequest(BaseModel):
    post_id: int
    mode: str = "AI"  # AI / MANUAL


class GenerateReplyResponse(BaseModel):
    success: bool
    message: str
    reply: str | None = None