"""Phase 5 – Financial Integrity ORM models.

Three new tables:
  vendor_bill_discrepancies  – records any mismatch detected when a vendor
                               invoice rate is compared against the contracted
                               rate at the time of shipment.
  agent_settlements          – captures the computed settlement amount, the
                               exact rate version used, and the shipment it
                               relates to, providing a complete audit trail.
  market_rates               – a lightweight table for storing external market
                               benchmark rates per lane, required by the
                               quarterly rate-review report (Phase 5.3) and
                               the rate-competitiveness analysis (Phase 7.4).
                               Market rate data is fed in by operations staff
                               or a future market-data integration; the system
                               never fabricates market data.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorBillDiscrepancy(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Records a detected mismatch between a vendor invoice rate and the
    applicable contracted rate for a shipment.

    ``status`` lifecycle: OPEN → UNDER_REVIEW → RESOLVED | WAIVED
    """

    __tablename__ = "vendor_bill_discrepancies"
    __table_args__ = (
        Index("ix_vbd_tenant_status", "tenant_id", "status"),
        Index("ix_vbd_vendor_id", "vendor_id"),
        Index("ix_vbd_shipment_id", "shipment_id"),
        Index("ix_vbd_detected_at", "detected_at"),
    )

    # Context references
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )

    # Rate references – both may be None if no contracted rate existed
    contracted_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rates.id"), nullable=True
    )
    contracted_rate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id"), nullable=True
    )

    # Human-readable references
    shipment_reference: Mapped[str | None] = mapped_column(Text)
    vendor_invoice_reference: Mapped[str | None] = mapped_column(Text)
    charge_code: Mapped[str | None] = mapped_column(Text)

    # Rate figures
    contracted_rate_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))
    invoiced_rate_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    variance_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)

    # Rate validity context
    rate_effective_date: Mapped[date | None] = mapped_column(Date)
    rate_expiry_date: Mapped[date | None] = mapped_column(Date)
    rate_was_expired_at_invoice_date: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    invoice_date: Mapped[date | None] = mapped_column(Date)

    # Workflow
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPEN", index=True
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)


class AgentSettlement(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Persists the computed settlement amount for an agent, with a full
    audit trail back to the exact rate version that was used.

    ``status`` lifecycle: DRAFT → APPROVED → PAID | CANCELLED
    """

    __tablename__ = "agent_settlements"
    __table_args__ = (
        Index("ix_as_tenant_status", "tenant_id", "status"),
        Index("ix_as_agent_id", "agent_id"),
        Index("ix_as_shipment_id", "shipment_id"),
        Index("ix_as_settlement_date", "settlement_date"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=True
    )

    # The specific rate agreement and version that produced the amount
    rate_agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_rate_agreements.id"), nullable=True
    )
    rate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id"), nullable=True
    )

    # Cost ledger entry integration
    cost_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id"), nullable=True
    )

    # Settlement figures
    base_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    rate_applied: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    settlement_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Audit fields
    rate_effective_date: Mapped[date | None] = mapped_column(Date)
    rate_expiry_date: Mapped[date | None] = mapped_column(Date)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    calculated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT", index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)


class MarketRate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Stores external/benchmark market rates per lane.

    This table is the data source for:
      • Phase 5.3 – Quarterly Rate Review (contracted vs market comparison)
      • Phase 7.4 – Rate Competitiveness Analysis

    Data is NOT auto-populated or fabricated by the system.  Operations staff
    or a future market-data integration feed values here.  The ``source``
    column records where the benchmark came from (e.g. "Freightos", "manual").
    """

    __tablename__ = "market_rates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "origin_location_id",
            "destination_location_id",
            "mode",
            "rate_type",
            "effective_date",
            "source",
            name="uq_market_rate",
        ),
        Index("ix_mr_tenant_lane", "tenant_id", "origin_location_id", "destination_location_id"),
        Index("ix_mr_effective_expiry", "effective_date", "expiry_date"),
    )

    origin_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
