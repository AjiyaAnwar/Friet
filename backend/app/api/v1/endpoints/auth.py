"""Authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, get_tenant_header
from app.db.session import get_db
from app.modules.auth.schemas import (
    LoginRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    TokenResponse,
    UserMeResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    tenant_code: Annotated[str, Depends(get_tenant_header)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    service = AuthService(session)
    result = await service.login(
        tenant_code,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    service = AuthService(session)
    result = await service.refresh(payload.refresh_token)
    await session.commit()
    return result


@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    service = AuthService(session)
    await service.logout(payload.refresh_token)
    await session.commit()


@router.get("/me", response_model=UserMeResponse)
async def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserMeResponse:
    service = AuthService(session)
    return await service.get_me(user.id, user.tenant_id)


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def enroll_mfa(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MfaEnrollResponse:
    service = AuthService(session)
    result = await service.enroll_mfa(user.id, user.tenant_id)
    await session.commit()
    return result


@router.post("/mfa/confirm", status_code=204)
async def confirm_mfa(
    payload: MfaVerifyRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    service = AuthService(session)
    await service.confirm_mfa(user.id, user.tenant_id, payload.totp_code)
    await session.commit()
