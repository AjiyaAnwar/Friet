"""Shipment Tracking Service (Phase 4.5)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import Shipment, TrackingEvent
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService
from app.modules.tracking.taxonomy import (
    EVENT_TAXONOMY,
    EventCategory,
    EventSource,
    get_category_for_event,
    validate_event_type,
)


class TrackingService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    async def record_event(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        event_type: str,
        location: str | None = None,
        event_time_original: str | None = None,
        event_time_utc: datetime | None = None,
        description: str | None = None,
        source: str = "MANUAL",
    ) -> dict[str, Any]:
        """Record a tracking event with taxonomy validation, UTC normalization, and audit logging."""
        is_valid, normalized_type, category = validate_event_type(event_type)
        if not is_valid or not normalized_type or not category:
            valid_sample = list(EVENT_TAXONOMY.keys())[:5]
            raise ValidationError(
                f"Invalid tracking event_type '{event_type}'. Must be one of ~60 standard taxonomy types (e.g., {', '.join(valid_sample)}...)"
            )

        # Normalize UTC timestamp
        if event_time_utc is None:
            utc_dt = datetime.now(timezone.utc)
        elif event_time_utc.tzinfo is None:
            utc_dt = event_time_utc.replace(tzinfo=timezone.utc)
        else:
            utc_dt = event_time_utc.astimezone(timezone.utc)

        # Standard description fallback
        standard_desc = EVENT_TAXONOMY[normalized_type]["description"]
        final_desc = description or standard_desc

        if self.session is None:
            # In-memory test double
            event_id = uuid.uuid4()
            return {
                "id": str(event_id),
                "shipment_id": str(shipment_id),
                "event_type": normalized_type,
                "category": category.value,
                "location": location,
                "event_time_original": event_time_original or str(utc_dt),
                "event_time_utc": utc_dt.isoformat(),
                "description": final_desc,
                "source": source.upper(),
                "created_by": str(actor_id) if actor_id else None,
            }

        # Verify shipment exists
        shipment = (
            await self.session.execute(
                select(Shipment).where(
                    Shipment.id == shipment_id,
                    Shipment.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not shipment:
            raise NotFoundError("Shipment not found")

        event = TrackingEvent(
            shipment_id=shipment_id,
            event_type=normalized_type,
            category=category.value,
            location=location,
            event_time_original=event_time_original or str(utc_dt),
            event_time_utc=utc_dt,
            event_time=utc_dt,
            description=final_desc,
            source=source.upper(),
            created_by=actor_id,
        )
        self.session.add(event)
        await self.session.flush()

        if self.audit and actor_id:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="shipment",
                entity_id=str(shipment_id),
                action="tracking.event_recorded",
                new_value={
                    "event_id": str(event.id),
                    "event_type": normalized_type,
                    "category": category.value,
                    "location": location,
                },
            )

        if self.outbox:
            await self.outbox.enqueue(
                event_type="tracking.event_recorded",
                tenant_id=tenant_id,
                aggregate_type="shipment",
                aggregate_id=shipment_id,
                payload={
                    "event_id": str(event.id),
                    "event_type": normalized_type,
                    "category": category.value,
                    "location": location,
                    "event_time_utc": utc_dt.isoformat(),
                },
            )

        return {
            "id": str(event.id),
            "shipment_id": str(event.shipment_id),
            "event_type": event.event_type,
            "category": event.category,
            "location": event.location,
            "event_time_original": event.event_time_original,
            "event_time_utc": str(event.event_time_utc),
            "description": event.description,
            "source": event.source,
            "created_by": str(event.created_by) if event.created_by else None,
            "created_at": str(event.created_at) if hasattr(event, "created_at") and event.created_at else None,
        }

    async def get_timeline(
        self,
        *,
        shipment_id: uuid.UUID,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get chronological event timeline for shipment, ordered most-recent first."""
        if self.session is None:
            return []

        stmt = (
            select(TrackingEvent)
            .where(TrackingEvent.shipment_id == shipment_id)
            .order_by(desc(TrackingEvent.event_time_utc), desc(TrackingEvent.created_at))
            .limit(limit)
        )

        if category:
            stmt = stmt.where(TrackingEvent.category == category.upper())

        events = (await self.session.execute(stmt)).scalars().all()

        return [
            {
                "id": str(e.id),
                "shipment_id": str(e.shipment_id),
                "event_type": e.event_type,
                "category": e.category or get_category_for_event(e.event_type),
                "location": e.location,
                "event_time_original": e.event_time_original,
                "event_time_utc": str(e.event_time_utc),
                "description": e.description,
                "source": e.source,
                "created_by": str(e.created_by) if e.created_by else None,
            }
            for e in events
        ]

    def get_taxonomy_catalog(self) -> list[dict[str, Any]]:
        """Return full event taxonomy catalog structured by category."""
        catalog = []
        for event_type, data in sorted(EVENT_TAXONOMY.items(), key=lambda x: (x[1]["category"].value, x[0])):
            catalog.append({
                "event_type": event_type,
                "category": data["category"].value,
                "description": data["description"],
            })
        return catalog

