"""FastAPI dependencies for auth, tenant context, and permissions."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db, set_tenant_context
from app.modules.identity.service import IdentityService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID | None
    permissions: set[str]
    roles: set[str]
    is_portal: bool


async def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUser | None:
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    user_id = uuid.UUID(payload["sub"])
    tenant_id = uuid.UUID(payload["tenant_id"])
    await set_tenant_context(session, tenant_id)

    identity = IdentityService(session)
    permissions, roles = await identity.get_user_permissions_and_roles(user_id)
    from app.core.permissions import PORTAL_ROLES

    is_portal = bool(roles & {r.value for r in PORTAL_ROLES})
    return CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        permissions=permissions,
        roles=roles,
        is_portal=is_portal,
    )


async def get_current_user(
    user: Annotated[CurrentUser | None, Depends(get_current_user_optional)],
) -> CurrentUser:
    if not user:
        raise UnauthorizedError()
    return user


def require_permission(permission: str):
    async def _checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if permission not in user.permissions:
            raise ForbiddenError(f"Missing permission: {permission}")
        if user.is_portal and permission.startswith(("finance:", "audit:", "role:")):
            raise ForbiddenError("Portal users cannot access internal endpoints")
        return user

    return _checker


async def get_tenant_header(
    x_tenant_code: Annotated[str | None, Header(alias="X-Tenant-Code")] = None,
) -> str:
    return x_tenant_code or "default"
