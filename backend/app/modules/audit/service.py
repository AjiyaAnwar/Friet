"""Audit trail service — append-only entity-aware logging."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditLog

SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "refresh_token",
    "access_token",
    "authorization",
    "mfa_secret",
    "tax_registration",
    "bank_details",
    "credit_limit_amount",
    "email",
    "phone",
}


def redact_payload(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return data
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_payload(value)
        else:
            redacted[key] = value
    return redacted


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        tenant_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        branch_id: uuid.UUID | None,
        entity_type: str,
        entity_id: str,
        action: str,
        previous_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            branch_id=branch_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            previous_value=redact_payload(previous_value),
            new_value=redact_payload(new_value),
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
