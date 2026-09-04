"""Exception Management Service (SRS Phase 4.7)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import Shipment, ShipmentException
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService
from app.modules.exceptions.escalations import evaluate_exception_escalations
from app.modules.exceptions.taxonomy import (
    VALID_DOMAINS,
    VALID_SEVERITIES,
    VALID_STATUSES,
    resolve_exception_type,
)


class ExceptionService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    async def create_exception(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        exception_type: str,
        description: str,
        severity: str | None = None,
        domain: str | None = None,
        financial_impact_estimated: float = 0.0,
        owner_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Raise a new shipment exception with taxonomy validation, escalation evaluation, and outbox emission."""
        tax_config = resolve_exception_type(exception_type)
        if not tax_config:
            raise ValidationError(f"Invalid exception type '{exception_type}'.")

        resolved_type = tax_config.code
        final_severity = (severity.upper() if severity else tax_config.default_severity)
        if final_severity not in VALID_SEVERITIES:
            raise ValidationError(f"Invalid severity '{final_severity}'. Must be one of {VALID_SEVERITIES}")

        final_domain = (domain.upper() if domain else tax_config.domain)
        if final_domain not in VALID_DOMAINS:
            raise ValidationError(f"Invalid domain '{final_domain}'. Must be one of {VALID_DOMAINS}")

        now = datetime.now(UTC)

        if not self.session:
            # In-memory test double fallback
            return {
                "id": str(uuid.uuid4()),
                "shipment_id": str(shipment_id),
                "tenant_id": str(tenant_id),
                "exception_type": resolved_type,
                "severity": final_severity,
                "domain": final_domain,
                "status": "OPEN",
                "description": description,
                "financial_impact_estimated": financial_impact_estimated,
                "owner_id": str(owner_id) if owner_id else None,
                "opened_at": now.isoformat(),
                "acknowledged_at": None,
                "resolved_at": None,
                "resolution_notes": None,
                "escalations": [],
            }

        # Verify shipment exists
        ship_stmt = select(Shipment).where(Shipment.id == shipment_id)
        ship_res = await self.session.execute(ship_stmt)
        shipment = ship_res.scalar_one_or_none()
        if not shipment:
            raise NotFoundError(f"Shipment {shipment_id} not found.")

        exc_record = ShipmentException(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            exception_type=resolved_type,
            severity=final_severity,
            domain=final_domain,
            status="OPEN",
            description=description,
            financial_impact_estimated=financial_impact_estimated,
            owner_id=owner_id,
            opened_at=now,
            acknowledged_at=None,
            resolved_at=None,
            resolution_notes=None,
        )
        self.session.add(exc_record)
        await self.session.flush()

        # Evaluate initial auto-escalations
        exc_dict = {
            "id": str(exc_record.id),
            "shipment_id": str(shipment_id),
            "exception_type": resolved_type,
            "severity": final_severity,
            "domain": final_domain,
            "status": "OPEN",
            "owner_id": str(owner_id) if owner_id else None,
            "financial_impact_estimated": financial_impact_estimated,
            "opened_at": now,
            "acknowledged_at": None,
        }
        escalations = evaluate_exception_escalations(exception=exc_dict, now=now)

        # Publish outbox events and audit logs
        if self.outbox:
            for esc in escalations:
                if esc.get("outbox_event"):
                    await self.outbox.enqueue(
                        event_type=esc["outbox_event"],
                        tenant_id=tenant_id,
                        aggregate_type="shipment_exception",
                        aggregate_id=exc_record.id,
                        payload={
                            "exception_id": str(exc_record.id),
                            "shipment_id": str(shipment_id),
                            "escalation": esc,
                            "exception_type": resolved_type,
                            "severity": final_severity,
                        },
                    )

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="shipment_exception",
                entity_id=str(exc_record.id),
                action="exception.created",
                new_value={
                    "exception_type": resolved_type,
                    "severity": final_severity,
                    "domain": final_domain,
                    "status": "OPEN",
                },
            )

        return {
            "id": str(exc_record.id),
            "shipment_id": str(shipment_id),
            "tenant_id": str(tenant_id),
            "exception_type": resolved_type,
            "severity": final_severity,
            "domain": final_domain,
            "status": "OPEN",
            "description": description,
            "financial_impact_estimated": float(financial_impact_estimated),
            "owner_id": str(owner_id) if owner_id else None,
            "opened_at": now.isoformat(),
            "acknowledged_at": None,
            "resolved_at": None,
            "resolution_notes": None,
            "escalations": escalations,
        }

    async def update_exception(
        self,
        *,
        exception_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        status: str | None = None,
        owner_id: uuid.UUID | None = None,
        resolution_notes: str | None = None,
        financial_impact_estimated: float | None = None,
    ) -> dict[str, Any]:
        """Update exception status, ownership, resolution notes, and financial impact."""
        if not self.session:
            return {
                "id": str(exception_id),
                "status": status or "OPEN",
                "owner_id": str(owner_id) if owner_id else None,
                "resolution_notes": resolution_notes,
            }

        stmt = select(ShipmentException).where(
            ShipmentException.id == exception_id,
            ShipmentException.tenant_id == tenant_id,
        )
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise NotFoundError(f"Exception {exception_id} not found.")

        now = datetime.now(UTC)
        prev_status = record.status

        if status:
            norm_status = status.strip().upper()
            if norm_status not in VALID_STATUSES:
                raise ValidationError(f"Invalid status '{norm_status}'. Must be one of {VALID_STATUSES}")
            record.status = norm_status

            if norm_status == "ACKNOWLEDGED" and record.acknowledged_at is None:
                record.acknowledged_at = now
            elif norm_status in {"RESOLVED", "CLOSED"} and record.resolved_at is None:
                record.resolved_at = now

        if owner_id is not None:
            record.owner_id = owner_id
            if record.acknowledged_at is None:
                record.acknowledged_at = now

        if resolution_notes is not None:
            record.resolution_notes = resolution_notes

        if financial_impact_estimated is not None:
            record.financial_impact_estimated = financial_impact_estimated

        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="shipment_exception",
                entity_id=str(exception_id),
                action="exception.updated",
                previous_value={"status": prev_status},
                new_value={"status": record.status, "owner_id": str(record.owner_id) if record.owner_id else None},
            )

        return {
            "id": str(record.id),
            "shipment_id": str(record.shipment_id),
            "tenant_id": str(record.tenant_id),
            "exception_type": record.exception_type,
            "severity": record.severity,
            "domain": record.domain,
            "status": record.status,
            "description": record.description,
            "financial_impact_estimated": float(record.financial_impact_estimated),
            "owner_id": str(record.owner_id) if record.owner_id else None,
            "opened_at": record.opened_at.isoformat() if record.opened_at else None,
            "acknowledged_at": record.acknowledged_at.isoformat() if record.acknowledged_at else None,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "resolution_notes": record.resolution_notes,
        }

    async def list_exceptions(
        self,
        *,
        tenant_id: uuid.UUID,
        shipment_id: uuid.UUID | None = None,
        status: str | None = None,
        severity: str | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """List exceptions with flexible status, severity, and domain filtering."""
        if not self.session:
            return []

        query = select(ShipmentException).where(ShipmentException.tenant_id == tenant_id)
        if shipment_id:
            query = query.where(ShipmentException.shipment_id == shipment_id)
        if status:
            query = query.where(ShipmentException.status == status.strip().upper())
        if severity:
            query = query.where(ShipmentException.severity == severity.strip().upper())
        if domain:
            query = query.where(ShipmentException.domain == domain.strip().upper())

        query = query.order_by(ShipmentException.opened_at.desc())
        res = await self.session.execute(query)
        rows = res.scalars().all()

        return [
            {
                "id": str(r.id),
                "shipment_id": str(r.shipment_id),
                "tenant_id": str(r.tenant_id),
                "exception_type": r.exception_type,
                "severity": r.severity,
                "domain": r.domain,
                "status": r.status,
                "description": r.description,
                "financial_impact_estimated": float(r.financial_impact_estimated),
                "owner_id": str(r.owner_id) if r.owner_id else None,
                "opened_at": r.opened_at.isoformat() if r.opened_at else None,
                "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
                "resolution_notes": r.resolution_notes,
            }
            for r in rows
        ]

    async def get_summary(
        self,
        *,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Aggregate exception counts by status, severity, domain, and total financial exposure for control tower."""
        if not self.session:
            return {
                "total_open": 0,
                "total_critical": 0,
                "total_financial_impact": 0.0,
                "by_status": {},
                "by_severity": {},
                "by_domain": {},
            }

        # Status aggregation
        status_stmt = (
            select(ShipmentException.status, func.count(ShipmentException.id))
            .where(ShipmentException.tenant_id == tenant_id)
            .group_by(ShipmentException.status)
        )
        status_res = await self.session.execute(status_stmt)
        by_status = {row[0]: row[1] for row in status_res.all()}

        # Severity aggregation
        sev_stmt = (
            select(ShipmentException.severity, func.count(ShipmentException.id))
            .where(ShipmentException.tenant_id == tenant_id)
            .group_by(ShipmentException.severity)
        )
        sev_res = await self.session.execute(sev_stmt)
        by_sev = {row[0]: row[1] for row in sev_res.all()}

        # Domain aggregation
        dom_stmt = (
            select(ShipmentException.domain, func.count(ShipmentException.id))
            .where(ShipmentException.tenant_id == tenant_id)
            .group_by(ShipmentException.domain)
        )
        dom_res = await self.session.execute(dom_stmt)
        by_dom = {row[0]: row[1] for row in dom_res.all()}

        # Total financial impact of open/active exceptions
        fin_stmt = (
            select(func.sum(ShipmentException.financial_impact_estimated))
            .where(
                ShipmentException.tenant_id == tenant_id,
                ShipmentException.status.in_(["OPEN", "ACKNOWLEDGED", "UNDER_INVESTIGATION"]),
            )
        )
        fin_res = await self.session.execute(fin_stmt)
        total_fin = float(fin_res.scalar() or 0.0)

        total_open = sum(count for st, count in by_status.items() if st in {"OPEN", "ACKNOWLEDGED", "UNDER_INVESTIGATION"})

        return {
            "total_open": total_open,
            "total_critical": by_sev.get("CRITICAL", 0),
            "total_financial_impact": total_fin,
            "by_status": by_status,
            "by_severity": by_sev,
            "by_domain": by_dom,
        }

