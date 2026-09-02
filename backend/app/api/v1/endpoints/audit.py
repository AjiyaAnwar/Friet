"""Audit log search API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.models.audit import AuditLog
from app.db.session import get_db

router = APIRouter()


@router.get("")
async def list_audit_logs(
    user: Annotated[CurrentUser, Depends(require_permission("audit:read"))],
    session: Annotated[AsyncSession, Depends(get_db)],
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> dict:
    stmt = select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    data = [
        {
            "id": str(r.id),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "action": r.action,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return {"data": data, "meta": {"total": len(data)}, "errors": []}
