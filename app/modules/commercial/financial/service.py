"""Phase 5 – Financial Integrity Service.

Business logic for:
  5.1 Vendor bill matching / contracted-rate validation
  5.2 Agent settlement rate management
  5.3 Quarterly rate review report
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.commercial import (
    Agent,
    AgentRateAgreement,
    Rate,
    RateLine,
    RateVersion,
)
from app.db.models.domain import CostLine, Shipment
from app.db.models.financial import FinancialEntry
from app.db.models.financial_integrity import (
    AgentSettlement,
    MarketRate,
    VendorBillDiscrepancy,
)
from app.db.models.reference import Location


# ---------------------------------------------------------------------------
# 5.1  Vendor bill matching / contracted-rate validation
# ---------------------------------------------------------------------------

class FinancialIntegrityService:
    """Encapsulates Phase 5 financial-integrity operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    async def _find_best_contracted_rate_version(
        self,
        *,
        vendor_id: uuid.UUID | None,
        origin_location_id: uuid.UUID | None,
        destination_location_id: uuid.UUID | None,
        mode: str | None,
        charge_code: str | None,
        on_date: date,
        tenant_id: uuid.UUID,
    ) -> tuple[Rate | None, RateVersion | None, RateLine | None]:
        """Return the (Rate, RateVersion, RateLine) that should have applied
        on *on_date* for this lane/vendor combination, respecting
        effective/expiry dates.  Returns (None, None, None) if no contracted
        rate exists.
        """
        # 1. Find the rate header that matches on_date within its validity window
        rate_q = (
            select(Rate)
            .where(
                Rate.tenant_id == tenant_id,
                Rate.effective_date <= on_date,
                Rate.expiry_date >= on_date,
                Rate.status.in_(["APPROVED", "ACTIVE"]),
            )
        )
        if vendor_id:
            # A contracted supplier is stored on Rate.vendor_id.  carrier_id
            # identifies a transport carrier and must not be substituted here.
            rate_q = rate_q.where(Rate.vendor_id == vendor_id)
        if origin_location_id:
            rate_q = rate_q.where(Rate.origin_location_id == origin_location_id)
        if destination_location_id:
            rate_q = rate_q.where(
                Rate.destination_location_id == destination_location_id
            )
        if mode:
            rate_q = rate_q.where(Rate.rate_type.ilike(f"%{mode}%"))

        rate_rows = (await self.session.execute(rate_q)).scalars().all()
        if not rate_rows:
            return None, None, None

        # 2. For each candidate rate, get the latest APPROVED version
        best: tuple[Rate, RateVersion, RateLine | None] | None = None
        for rate in rate_rows:
            ver_q = (
                select(RateVersion)
                .where(
                    RateVersion.rate_id == rate.id,
                    RateVersion.approval_status == "APPROVED",
                )
                .order_by(RateVersion.version_number.desc())
                .limit(1)
            )
            version = (await self.session.execute(ver_q)).scalar_one_or_none()
            if not version:
                continue

            # 3. Optionally find the specific rate line by charge_code
            line = None
            if charge_code:
                line_q = select(RateLine).where(
                    RateLine.rate_version_id == version.id,
                    RateLine.charge_code == charge_code,
                )
                line = (await self.session.execute(line_q)).scalar_one_or_none()

            best = (rate, version, line)
            break  # take the first match; extend with ranking logic if needed

        if best is None:
            return None, None, None
        return best

    # ------------------------------------------------------------------
    # 5.1  Match a vendor invoice line against the contracted rate
    # ------------------------------------------------------------------

    async def match_vendor_bill(
        self,
        *,
        tenant_id: uuid.UUID,
        vendor_id: str | None,
        shipment_id: str | None,
        shipment_reference: str | None,
        vendor_invoice_reference: str | None,
        charge_code: str | None,
        invoiced_rate_amount: float,
        currency_code: str,
        invoice_date: date,
        origin_location_id: str | None = None,
        destination_location_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Compare the vendor-invoiced rate to the applicable contracted rate.

        Returns a dict describing the match result and persists a
        ``VendorBillDiscrepancy`` record if a mismatch is found (or if no
        contracted rate exists).
        """
        v_uuid = _parse_uuid(vendor_id)
        s_uuid = _parse_uuid(shipment_id)
        o_uuid = _parse_uuid(origin_location_id)
        d_uuid = _parse_uuid(destination_location_id)

        rate, version, line = await self._find_best_contracted_rate_version(
            vendor_id=v_uuid,
            origin_location_id=o_uuid,
            destination_location_id=d_uuid,
            mode=mode,
            charge_code=charge_code,
            on_date=invoice_date,
            tenant_id=tenant_id,
        )

        contracted_amount: float | None = None
        rate_was_expired = False

        if line:
            contracted_amount = float(line.amount)
        elif rate and version:
            # No specific line; use zero to highlight that a rate existed but
            # the specific charge code could not be resolved.
            contracted_amount = None

        if rate and invoice_date > rate.expiry_date:
            rate_was_expired = True

        # Determine variance
        if contracted_amount is not None:
            variance = round(invoiced_rate_amount - contracted_amount, 4)
            matched = abs(variance) < 0.0001 and not rate_was_expired
        else:
            variance = invoiced_rate_amount  # full amount is unexplained
            matched = False

        discrepancy_needed = not matched or rate is None or rate_was_expired

        db_record: VendorBillDiscrepancy | None = None
        if discrepancy_needed:
            db_record = VendorBillDiscrepancy(
                tenant_id=tenant_id,
                shipment_id=s_uuid,
                vendor_id=v_uuid,
                contracted_rate_id=rate.id if rate else None,
                contracted_rate_version_id=version.id if version else None,
                shipment_reference=shipment_reference,
                vendor_invoice_reference=vendor_invoice_reference,
                charge_code=charge_code,
                contracted_rate_amount=contracted_amount,
                invoiced_rate_amount=invoiced_rate_amount,
                variance_amount=variance,
                currency_code=currency_code,
                rate_effective_date=rate.effective_date if rate else None,
                rate_expiry_date=rate.expiry_date if rate else None,
                rate_was_expired_at_invoice_date=rate_was_expired,
                invoice_date=invoice_date,
                status="OPEN",
                detected_at=datetime.now(UTC),
            )
            self.session.add(db_record)
            await self.session.flush()

        return {
            "matched": matched,
            "contracted_rate_id": str(rate.id) if rate else None,
            "contracted_rate_version_id": str(version.id) if version else None,
            "contracted_amount": contracted_amount,
            "invoiced_amount": invoiced_rate_amount,
            "variance": variance,
            "currency_code": currency_code,
            "rate_was_expired": rate_was_expired,
            "discrepancy_id": str(db_record.id) if db_record else None,
            "status": "OPEN" if discrepancy_needed else "MATCHED",
        }

    async def get_discrepancy(
        self, discrepancy_id: str, tenant_id: uuid.UUID
    ) -> dict[str, Any]:
        uid = _parse_uuid(discrepancy_id)
        if not uid:
            raise NotFoundError(f"Discrepancy '{discrepancy_id}' not found")
        stmt = select(VendorBillDiscrepancy).where(
            VendorBillDiscrepancy.id == uid,
            VendorBillDiscrepancy.tenant_id == tenant_id,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not row:
            raise NotFoundError(f"Discrepancy '{discrepancy_id}' not found")
        return _discrepancy_to_dict(row)

    async def list_discrepancies(
        self,
        tenant_id: uuid.UUID,
        status: str | None = None,
        vendor_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(VendorBillDiscrepancy).where(
            VendorBillDiscrepancy.tenant_id == tenant_id
        )
        if status:
            stmt = stmt.where(VendorBillDiscrepancy.status == status)
        v_uuid = _parse_uuid(vendor_id)
        if v_uuid:
            stmt = stmt.where(VendorBillDiscrepancy.vendor_id == v_uuid)
        stmt = stmt.order_by(VendorBillDiscrepancy.detected_at.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_discrepancy_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 5.2  Agent settlement
    # ------------------------------------------------------------------

    async def calculate_agent_settlement(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_id: str,
        shipment_id: str | None,
        base_amount: float,
        currency_code: str,
        settlement_date: date,
        calculated_by: uuid.UUID | None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Find the applicable agent rate agreement (respecting effective/expiry
        dates), compute the settlement amount, and persist an AgentSettlement
        record.
        """
        a_uuid = _parse_uuid(agent_id)
        if not a_uuid:
            raise ValidationError(f"Invalid agent_id: {agent_id}")

        # Verify agent belongs to tenant
        agent_stmt = select(Agent).where(
            Agent.id == a_uuid, Agent.tenant_id == tenant_id
        )
        agent = (await self.session.execute(agent_stmt)).scalar_one_or_none()
        if not agent:
            raise NotFoundError(f"Agent '{agent_id}' not found")

        # Find the best rate agreement active on settlement_date
        # AgentRateAgreement has effective_date / expiry_date columns
        ara_stmt = (
            select(AgentRateAgreement)
            .join(Rate, AgentRateAgreement.rate_id == Rate.id)
            .where(
                AgentRateAgreement.agent_id == a_uuid,
                AgentRateAgreement.effective_date <= settlement_date,
                AgentRateAgreement.expiry_date >= settlement_date,
            )
            .order_by(AgentRateAgreement.effective_date.desc())
            .limit(1)
        )
        agreement = (await self.session.execute(ara_stmt)).scalar_one_or_none()

        # If no agreement exists we still create the record but flag it
        rate_applied: float = 0.0
        rate_version_id: uuid.UUID | None = None
        rate_effective: date | None = None
        rate_expiry: date | None = None
        agreement_id: uuid.UUID | None = None

        if agreement:
            agreement_id = agreement.id
            rate_effective = agreement.effective_date
            rate_expiry = agreement.expiry_date
            # Get latest APPROVED rate version to extract the rate amount
            ver_stmt = (
                select(RateVersion)
                .where(
                    RateVersion.rate_id == agreement.rate_id,
                    RateVersion.approval_status == "APPROVED",
                )
                .order_by(RateVersion.version_number.desc())
                .limit(1)
            )
            version = (await self.session.execute(ver_stmt)).scalar_one_or_none()
            if version:
                rate_version_id = version.id
                # Use the first rate line's amount as the settlement rate
                line_stmt = (
                    select(RateLine)
                    .where(RateLine.rate_version_id == version.id)
                    .limit(1)
                )
                line = (await self.session.execute(line_stmt)).scalar_one_or_none()
                if line:
                    rate_applied = float(line.amount)

        settlement_amount = round(base_amount * rate_applied, 4)

        s_uuid = _parse_uuid(shipment_id)

        # 1. Post to existing financial cost ledger (financial_entries)
        ledger_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=s_uuid,
            entry_date=settlement_date,
            entry_type="AGENT_SETTLEMENT",
            debit_amount=settlement_amount,
            credit_amount=0.0,
            currency_code=currency_code,
            description=(
                f"Agent settlement for agent {a_uuid} on agreement "
                f"{agreement_id or 'NONE'} using rate version {rate_version_id or 'NONE'}"
            ),
            status="POSTED",
        )
        self.session.add(ledger_entry)
        await self.session.flush()

        # 2. If shipment_id is provided and agent has an associated vendor_id, update cost_lines
        if s_uuid and getattr(agent, "vendor_id", None):
            cost_line = CostLine(
                shipment_id=s_uuid,
                vendor_id=agent.vendor_id,
                amount=settlement_amount,
            )
            self.session.add(cost_line)

        # 3. Persist auditable AgentSettlement record referencing the cost ledger entry
        record = AgentSettlement(
            tenant_id=tenant_id,
            agent_id=a_uuid,
            shipment_id=s_uuid,
            rate_agreement_id=agreement_id,
            rate_version_id=rate_version_id,
            cost_entry_id=ledger_entry.id,
            base_amount=base_amount,
            rate_applied=rate_applied,
            settlement_amount=settlement_amount,
            currency_code=currency_code,
            settlement_date=settlement_date,
            rate_effective_date=rate_effective,
            rate_expiry_date=rate_expiry,
            calculated_at=datetime.now(UTC),
            calculated_by=calculated_by,
            status="DRAFT",
            notes=notes,
        )
        self.session.add(record)
        await self.session.flush()

        return {
            "settlement_id": str(record.id),
            "cost_entry_id": str(ledger_entry.id),
            "agent_id": str(a_uuid),
            "shipment_id": str(s_uuid) if s_uuid else None,
            "rate_agreement_id": str(agreement_id) if agreement_id else None,
            "rate_version_id": str(rate_version_id) if rate_version_id else None,
            "rate_applied": rate_applied,
            "base_amount": base_amount,
            "settlement_amount": settlement_amount,
            "currency_code": currency_code,
            "settlement_date": str(settlement_date),
            "rate_effective_date": str(rate_effective) if rate_effective else None,
            "rate_expiry_date": str(rate_expiry) if rate_expiry else None,
            "has_active_agreement": agreement is not None,
            "status": "DRAFT",
        }

    async def get_settlement(
        self, settlement_id: str, tenant_id: uuid.UUID
    ) -> dict[str, Any]:
        uid = _parse_uuid(settlement_id)
        if not uid:
            raise NotFoundError(f"Settlement '{settlement_id}' not found")
        stmt = select(AgentSettlement).where(
            AgentSettlement.id == uid,
            AgentSettlement.tenant_id == tenant_id,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if not row:
            raise NotFoundError(f"Settlement '{settlement_id}' not found")
        return _settlement_to_dict(row)

    # ------------------------------------------------------------------
    # 5.3  Quarterly rate review report
    # ------------------------------------------------------------------

    async def quarterly_rate_review(
        self,
        *,
        tenant_id: uuid.UUID,
        as_of_date: date | None = None,
        mode: str | None = None,
        origin_location_id: str | None = None,
        destination_location_id: str | None = None,
        warning_days: int = 90,
    ) -> dict[str, Any]:
        """Compare contracted rates against market rates for the tenant's lanes.

        Returns per-lane comparisons, including:
          - contracted rate amount
          - market benchmark amount (if available)
          - variance and competitiveness indicator
          - expiry status

        If no market data exists for a lane, the lane still appears in the
        report but with market_amount=null and competitiveness="UNKNOWN".
        """
        today = as_of_date or date.today()

        # --- 1. Active contracted rates within validity window ---
        rate_q = (
            select(Rate)
            .where(
                Rate.tenant_id == tenant_id,
                Rate.effective_date <= today,
                Rate.expiry_date >= today,
                Rate.status.in_(["APPROVED", "ACTIVE", "DRAFT"]),
            )
        )
        if mode:
            rate_q = rate_q.where(Rate.rate_type.ilike(f"%{mode}%"))
        o_uuid = _parse_uuid(origin_location_id)
        d_uuid = _parse_uuid(destination_location_id)
        if o_uuid:
            rate_q = rate_q.where(Rate.origin_location_id == o_uuid)
        if d_uuid:
            rate_q = rate_q.where(Rate.destination_location_id == d_uuid)

        rates = (await self.session.execute(rate_q)).scalars().all()

        # --- 2. Soon-to-expire rates (within warning_days but currently valid) ---
        expiring_soon_q = (
            select(Rate)
            .where(
                Rate.tenant_id == tenant_id,
                Rate.effective_date <= today,
                Rate.expiry_date >= today,
                Rate.expiry_date <= date.fromordinal(today.toordinal() + warning_days),
            )
        )
        expiring_ids = {
            r.id
            for r in (await self.session.execute(expiring_soon_q)).scalars().all()
        }

        # --- 3. Get market rates for these lanes ---
        # Collect unique (origin, destination, rate_type) combos
        lanes = {
            (r.origin_location_id, r.destination_location_id, r.rate_type)
            for r in rates
            if r.origin_location_id and r.destination_location_id
        }

        market_lookup: dict[tuple, float] = {}
        for origin_id, dest_id, rate_type in lanes:
            mr_stmt = (
                select(MarketRate)
                .where(
                    MarketRate.tenant_id == tenant_id,
                    MarketRate.origin_location_id == origin_id,
                    MarketRate.destination_location_id == dest_id,
                    MarketRate.rate_type == rate_type,
                    MarketRate.effective_date <= today,
                    or_(
                        MarketRate.expiry_date.is_(None),
                        MarketRate.expiry_date >= today,
                    ),
                )
                .order_by(MarketRate.effective_date.desc())
                .limit(1)
            )
            mr = (await self.session.execute(mr_stmt)).scalar_one_or_none()
            if mr:
                market_lookup[(origin_id, dest_id, rate_type)] = float(mr.amount)

        # --- 4. Build per-lane entries ---
        # For each rate, get the latest APPROVED version's first line amount
        entries = []
        for rate in rates:
            ver_stmt = (
                select(RateVersion)
                .where(
                    RateVersion.rate_id == rate.id,
                    RateVersion.approval_status == "APPROVED",
                )
                .order_by(RateVersion.version_number.desc())
                .limit(1)
            )
            version = (await self.session.execute(ver_stmt)).scalar_one_or_none()
            contracted_amount: float | None = None
            if version:
                line_stmt = (
                    select(RateLine)
                    .where(RateLine.rate_version_id == version.id)
                    .limit(1)
                )
                line = (await self.session.execute(line_stmt)).scalar_one_or_none()
                if line:
                    contracted_amount = float(line.amount)

            market_amount = market_lookup.get(
                (rate.origin_location_id, rate.destination_location_id, rate.rate_type)
            )
            variance = None
            variance_pct = None
            competitiveness = "UNKNOWN"
            if contracted_amount is not None and market_amount is not None:
                variance = round(contracted_amount - market_amount, 4)
                variance_pct = (
                    round(variance / market_amount * 100, 2)
                    if market_amount != 0
                    else None
                )
                if abs(variance) < 0.01 * market_amount:
                    competitiveness = "COMPETITIVE"
                elif contracted_amount < market_amount:
                    competitiveness = "BELOW_MARKET"
                else:
                    competitiveness = "ABOVE_MARKET"

            expiring = rate.id in expiring_ids
            days_to_expiry = (rate.expiry_date - today).days

            entries.append(
                {
                    "rate_id": str(rate.id),
                    "rate_number": rate.rate_number,
                    "rate_type": rate.rate_type,
                    "rate_category": rate.rate_category,
                    "origin_location_id": (
                        str(rate.origin_location_id) if rate.origin_location_id else None
                    ),
                    "destination_location_id": (
                        str(rate.destination_location_id)
                        if rate.destination_location_id
                        else None
                    ),
                    "currency_code": rate.currency_code,
                    "contracted_amount": contracted_amount,
                    "market_amount": market_amount,
                    "variance": variance,
                    "variance_pct": variance_pct,
                    "competitiveness": competitiveness,
                    "effective_date": str(rate.effective_date),
                    "expiry_date": str(rate.expiry_date),
                    "days_to_expiry": days_to_expiry,
                    "expiring_soon": expiring,
                    "needs_review": expiring or competitiveness == "ABOVE_MARKET",
                    "rate_version_id": str(version.id) if version else None,
                    "rate_status": rate.status,
                }
            )

        # Summary
        total = len(entries)
        competitive = sum(1 for e in entries if e["competitiveness"] == "COMPETITIVE")
        above = sum(1 for e in entries if e["competitiveness"] == "ABOVE_MARKET")
        below = sum(1 for e in entries if e["competitiveness"] == "BELOW_MARKET")
        unknown = sum(1 for e in entries if e["competitiveness"] == "UNKNOWN")
        expiring_count = sum(1 for e in entries if e["expiring_soon"])
        needs_review = sum(1 for e in entries if e["needs_review"])

        return {
            "as_of_date": str(today),
            "total_rates": total,
            "competitive": competitive,
            "above_market": above,
            "below_market": below,
            "market_data_unavailable": unknown,
            "expiring_soon": expiring_count,
            "needs_review": needs_review,
            "entries": entries,
        }

    # ------------------------------------------------------------------
    # Market rate CRUD (for 5.3 / 7.4 data feeding)
    # ------------------------------------------------------------------

    async def create_market_rate(
        self, data: dict[str, Any], tenant_id: uuid.UUID
    ) -> dict[str, Any]:
        o_uuid = _parse_uuid(data.get("origin_location_id"))
        d_uuid = _parse_uuid(data.get("destination_location_id"))
        if not o_uuid or not d_uuid:
            raise ValidationError("origin_location_id and destination_location_id are required UUIDs")

        eff = (
            date.fromisoformat(data["effective_date"])
            if isinstance(data["effective_date"], str)
            else data["effective_date"]
        )
        exp = None
        if data.get("expiry_date"):
            exp = (
                date.fromisoformat(data["expiry_date"])
                if isinstance(data["expiry_date"], str)
                else data["expiry_date"]
            )

        mr = MarketRate(
            tenant_id=tenant_id,
            origin_location_id=o_uuid,
            destination_location_id=d_uuid,
            mode=data["mode"],
            rate_type=data["rate_type"],
            amount=data["amount"],
            currency_code=data["currency_code"],
            effective_date=eff,
            expiry_date=exp,
            source=data.get("source", "manual"),
            notes=data.get("notes"),
        )
        self.session.add(mr)
        await self.session.flush()
        return _market_rate_to_dict(mr)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _parse_uuid(val: Any) -> uuid.UUID | None:
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


def _discrepancy_to_dict(r: VendorBillDiscrepancy) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "shipment_id": str(r.shipment_id) if r.shipment_id else None,
        "vendor_id": str(r.vendor_id) if r.vendor_id else None,
        "contracted_rate_id": str(r.contracted_rate_id) if r.contracted_rate_id else None,
        "contracted_rate_version_id": str(r.contracted_rate_version_id) if r.contracted_rate_version_id else None,
        "shipment_reference": r.shipment_reference,
        "vendor_invoice_reference": r.vendor_invoice_reference,
        "charge_code": r.charge_code,
        "contracted_rate_amount": float(r.contracted_rate_amount) if r.contracted_rate_amount is not None else None,
        "invoiced_rate_amount": float(r.invoiced_rate_amount),
        "variance_amount": float(r.variance_amount),
        "currency_code": r.currency_code,
        "rate_effective_date": str(r.rate_effective_date) if r.rate_effective_date else None,
        "rate_expiry_date": str(r.rate_expiry_date) if r.rate_expiry_date else None,
        "rate_was_expired_at_invoice_date": r.rate_was_expired_at_invoice_date,
        "invoice_date": str(r.invoice_date) if r.invoice_date else None,
        "status": r.status,
        "detected_at": r.detected_at.isoformat(),
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "resolution_notes": r.resolution_notes,
    }


def _settlement_to_dict(r: AgentSettlement) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "agent_id": str(r.agent_id),
        "shipment_id": str(r.shipment_id) if r.shipment_id else None,
        "rate_agreement_id": str(r.rate_agreement_id) if r.rate_agreement_id else None,
        "rate_version_id": str(r.rate_version_id) if r.rate_version_id else None,
        "cost_entry_id": str(r.cost_entry_id) if r.cost_entry_id else None,
        "base_amount": float(r.base_amount),
        "rate_applied": float(r.rate_applied),
        "settlement_amount": float(r.settlement_amount),
        "currency_code": r.currency_code,
        "settlement_date": str(r.settlement_date),
        "rate_effective_date": str(r.rate_effective_date) if r.rate_effective_date else None,
        "rate_expiry_date": str(r.rate_expiry_date) if r.rate_expiry_date else None,
        "calculated_at": r.calculated_at.isoformat(),
        "status": r.status,
        "notes": r.notes,
    }


def _market_rate_to_dict(r: MarketRate) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "origin_location_id": str(r.origin_location_id),
        "destination_location_id": str(r.destination_location_id),
        "mode": r.mode,
        "rate_type": r.rate_type,
        "amount": float(r.amount),
        "currency_code": r.currency_code,
        "effective_date": str(r.effective_date),
        "expiry_date": str(r.expiry_date) if r.expiry_date else None,
        "source": r.source,
        "notes": r.notes,
    }
