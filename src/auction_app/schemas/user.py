"""User Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    display_name: str
    email: str


class UserResponse(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}
