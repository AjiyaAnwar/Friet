"""Transactional outbox for domain events."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.events import OutboxEvent


class OutboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        event_type: str,
        tenant_id: uuid.UUID,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> OutboxEvent:
        event = OutboxEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
            publication_status="PENDING",
        )
        self.session.add(event)
        await self.session.flush()
        return event
