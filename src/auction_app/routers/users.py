"""User router — POST /users."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.database import get_session
from auction_app.models.user import User
from auction_app.schemas.user import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=201, response_model=UserResponse)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    """Register a new user. Returns 409 if email already exists."""
    # Check for duplicate email
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        display_name=data.display_name,
        email=data.email,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)
