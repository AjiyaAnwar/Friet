"""ETA/ETD Multi-Version Tracking & Cascade Service (SRS Phase 4.6)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import EtaHistory, Shipment, ShipmentLeg
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService
from app.modules.eta.alerts import evaluate_eta_deviations
from app.modules.eta.cascade import calculate_leg_cascade


class EtaService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    async def record_version(
        self,
        *,
        shipment_id: uuid.UUID,
        leg_id: uuid.UUID,
        type: str,
        value: datetime,
        source: str = "MANUAL",
        reason: str | None = None,
        recorded_by: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        has_firm_delivery_commitment: bool = False,
    ) -> dict[str, Any]:
        """Record an immutable new ETA or ETD version and trigger downstream multi-leg cascade."""
        norm_type = type.strip().upper()
        if norm_type not in {"ETA", "ETD"}:
            raise ValidationError(f"Invalid type '{type}'. Must be 'ETA' or 'ETD'.")

        valid_sources = {"QUOTATION", "BOOKING", "CARRIER_API", "MANUAL", "TERMINAL", "AUTO_CASCADE"}
        norm_source = source.strip().upper()
        if norm_source not in valid_sources:
            raise ValidationError(f"Invalid source '{source}'. Must be one of {valid_sources}.")

        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)

        now = datetime.now(UTC)

        if not self.session:
            # In-memory test double fallback
            return {
                "id": str(uuid.uuid4()),
                "shipment_id": str(shipment_id),
                "leg_id": str(leg_id),
                "type": norm_type,
                "version": 1,
                "value": value.isoformat(),
                "source": norm_source,
                "reason": reason,
                "recorded_by": str(recorded_by) if recorded_by else None,
                "recorded_at": now.isoformat(),
                "cascaded_updates": [],
                "alerts": [],
            }

        # 1. Verify Leg and Shipment exist
        leg_stmt = select(ShipmentLeg).where(
            ShipmentLeg.id == leg_id,
            ShipmentLeg.shipment_id == shipment_id,
        )
        leg_res = await self.session.execute(leg_stmt)
        leg = leg_res.scalar_one_or_none()
        if not leg:
            raise NotFoundError(f"Shipment leg {leg_id} not found on shipment {shipment_id}")

        # 2. Get highest existing version for this leg and type (append-only)
        ver_stmt = (
            select(EtaHistory)
            .where(
                EtaHistory.leg_id == leg_id,
                EtaHistory.type == norm_type,
            )
            .order_by(EtaHistory.version.desc())
        )
        ver_res = await self.session.execute(ver_stmt)
        latest_history = ver_res.scalars().first()
        next_version = (latest_history.version + 1) if latest_history else 1

        # 3. Create new immutable version record
        new_record = EtaHistory(
            shipment_id=shipment_id,
            leg_id=leg_id,
            type=norm_type,
            version=next_version,
            value=value,
            source=norm_source,
            reason=reason,
            recorded_by=recorded_by,
            recorded_at=now,
        )
        self.session.add(new_record)

        # 4. Update current value on ShipmentLeg entity
        if norm_type == "ETA":
            leg.eta = value
        else:
            leg.etd = value

        await self.session.flush()

        # 5. Multi-leg cascade when ETA changes
        cascaded_records_out: list[dict[str, Any]] = []
        if norm_type == "ETA":
            # Fetch all legs for this shipment ordered by created_at / id
            legs_stmt = (
                select(ShipmentLeg)
                .where(ShipmentLeg.shipment_id == shipment_id)
                .order_by(ShipmentLeg.created_at.asc())
            )
            legs_res = await self.session.execute(legs_stmt)
            all_legs = legs_res.scalars().all()

            legs_dicts = [
                {
                    "id": str(l.id),
                    "origin": l.origin,
                    "destination": l.destination,
                    "etd": l.etd,
                    "eta": l.eta,
                }
                for l in all_legs
            ]

            cascade_plan = calculate_leg_cascade(
                legs=legs_dicts,
                changed_leg_id=str(leg_id),
                new_eta=value,
            )

            for item in cascade_plan:
                c_leg_id = uuid.UUID(item["leg_id"])
                c_type = item["type"]
                c_val = item["value"]

                # Find latest version for cascaded leg
                c_ver_stmt = (
                    select(EtaHistory)
                    .where(
                        EtaHistory.leg_id == c_leg_id,
                        EtaHistory.type == c_type,
                    )
                    .order_by(EtaHistory.version.desc())
                )
                c_ver_res = await self.session.execute(c_ver_stmt)
                c_latest = c_ver_res.scalars().first()
                c_next_ver = (c_latest.version + 1) if c_latest else 1

                c_history = EtaHistory(
                    shipment_id=shipment_id,
                    leg_id=c_leg_id,
                    type=c_type,
                    version=c_next_ver,
                    value=c_val,
                    source=item["source"],
                    reason=item["reason"],
                    recorded_by=recorded_by,
                    recorded_at=now,
                )
                self.session.add(c_history)

                # Update leg entity
                target_leg = next((l for l in all_legs if l.id == c_leg_id), None)
                if target_leg:
                    if c_type == "ETA":
                        target_leg.eta = c_val
                    else:
                        target_leg.etd = c_val

                cascaded_records_out.append({
                    "leg_id": str(c_leg_id),
                    "type": c_type,
                    "version": c_next_ver,
                    "value": c_val.isoformat(),
                    "source": item["source"],
                    "reason": item["reason"],
                })

            if cascade_plan:
                await self.session.flush()

        # 6. Evaluate Deviation Alerts across the shipment
        all_hist_stmt = (
            select(EtaHistory)
            .where(EtaHistory.shipment_id == shipment_id)
            .order_by(EtaHistory.version.asc())
        )
        all_hist_res = await self.session.execute(all_hist_stmt)
        all_history = all_hist_res.scalars().all()

        hist_dicts = [
            {
                "shipment_id": str(h.shipment_id),
                "leg_id": str(h.leg_id),
                "type": h.type,
                "version": h.version,
                "value": h.value,
            }
            for h in all_history
        ]

        alerts = evaluate_eta_deviations(
            records=hist_dicts,
            has_firm_delivery_commitment=has_firm_delivery_commitment,
        )

        # 7. Publish outbox events for critical alerts
        if tenant_id and self.outbox:
            for alert in alerts:
                if alert.get("publish_customer_notification"):
                    await self.outbox.enqueue(
                        event_type="customer.notification",
                        tenant_id=tenant_id,
                        aggregate_type="shipment",
                        aggregate_id=shipment_id,
                        payload={
                            "alert": alert,
                            "notification_channel": "EMAIL_AND_PORTAL",
                            "message": alert["message"],
                        },
                    )

            if self.audit:
                await self.audit.record(
                    tenant_id=tenant_id,
                    user_id=recorded_by,
                    branch_id=None,
                    entity_type="shipment_leg",
                    entity_id=str(leg_id),
                    action="eta.version_recorded",
                    new_value={
                        "type": norm_type,
                        "version": next_version,
                        "value": value.isoformat(),
                        "source": norm_source,
                    },
                )

        return {
            "id": str(new_record.id),
            "shipment_id": str(shipment_id),
            "leg_id": str(leg_id),
            "type": norm_type,
            "version": next_version,
            "value": value.isoformat(),
            "source": norm_source,
            "reason": reason,
            "recorded_by": str(recorded_by) if recorded_by else None,
            "recorded_at": now.isoformat(),
            "cascaded_updates": cascaded_records_out,
            "alerts": alerts,
        }

    async def get_leg_history(
        self,
        *,
        shipment_id: uuid.UUID,
        leg_id: uuid.UUID,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get ordered version history for a leg (never overwritten, ordered ascending)."""
        if not self.session:
            return []

        query = select(EtaHistory).where(
            EtaHistory.shipment_id == shipment_id,
            EtaHistory.leg_id == leg_id,
        )
        if type:
            query = query.where(EtaHistory.type == type.strip().upper())

        query = query.order_by(EtaHistory.type.asc(), EtaHistory.version.asc())
        res = await self.session.execute(query)
        rows = res.scalars().all()

        return [
            {
                "id": str(r.id),
                "shipment_id": str(r.shipment_id),
                "leg_id": str(r.leg_id),
                "type": r.type,
                "version": r.version,
                "value": r.value.isoformat() if r.value else None,
                "source": r.source,
                "reason": r.reason,
                "recorded_by": str(r.recorded_by) if r.recorded_by else None,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in rows
        ]
