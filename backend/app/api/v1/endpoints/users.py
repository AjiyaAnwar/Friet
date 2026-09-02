"""User management endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.core.exceptions import NotFoundError
from app.db.models.identity import User
from app.db.session import get_db
from app.modules.auth.service import AuthService

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    status: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    status: str

    model_config = {"from_attributes": True}


@router.get("")
async def list_users(
    user: Annotated[CurrentUser, Depends(require_permission("user:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await session.execute(select(User).where(User.tenant_id == user.tenant_id).limit(50))
    items = [UserOut.model_validate(u) for u in result.scalars()]
    return {"data": items, "meta": {"total": len(items)}, "errors": []}


@router.post("")
async def create_user(
    payload: UserCreate,
    user: Annotated[CurrentUser, Depends(require_permission("user:create"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    new_user = User(
        tenant_id=user.tenant_id,
        email=payload.email.lower(),
        password_hash=AuthService.hash_password(payload.password),
        full_name=payload.full_name,
        created_by=user.id,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return {"data": UserOut.model_validate(new_user), "meta": {}, "errors": []}


@router.get("/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    user: Annotated[CurrentUser, Depends(require_permission("user:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == user.tenant_id)
    )
    found = result.scalar_one_or_none()
    if not found:
        raise NotFoundError("User not found")
    return {"data": UserOut.model_validate(found), "meta": {}, "errors": []}


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    user: Annotated[CurrentUser, Depends(require_permission("user:update"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await session.execute(
        select(User).where(User.id == user_id, User.tenant_id == user.tenant_id)
    )
    found = result.scalar_one_or_none()
    if not found:
        raise NotFoundError("User not found")
    if payload.full_name is not None:
        found.full_name = payload.full_name
    if payload.status is not None:
        found.status = payload.status
    found.updated_by = user.id
    await session.commit()
    await session.refresh(found)
    return {"data": UserOut.model_validate(found), "meta": {}, "errors": []}
