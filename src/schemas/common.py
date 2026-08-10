"""Generic response envelope matching the Django API shape."""
from typing import Any, Optional
from pydantic import BaseModel


class OkResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[Any] = None


class ErrResponse(BaseModel):
    success: bool = False
    message: str
    errors: Any = {}