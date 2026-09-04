"""Financial ledger and reconciliation infrastructure."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FinancialEntry(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "financial_entries"

    shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id")
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    debit_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id")
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    revenue_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revenue_lines.id")
    )
    cost_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_lines.id")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="POSTED")


class ReconciliationVariance(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "reconciliation_variances"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expected_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    actual_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    variance_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
