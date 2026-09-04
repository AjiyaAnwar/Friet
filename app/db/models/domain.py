"""MVP operational domain models: booking, shipment, tracking, finance."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import (
    AuditActorMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Booking(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bookings"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Shipment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "shipments"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, unique=True
    )
    # The booking FK is retained for backward compatibility with Team 1's
    # existing shipment API.  Commercial acceptance also records its ERD
    # handoff to the accepted job explicitly.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), unique=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    master_shipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id")
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)


class ShipmentLeg(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shipment_legs"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    etd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Container(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "containers"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False
    )
    container_no: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)


class Cargo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cargo"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False
    )
    weight: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)


class Package(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "packages"

    cargo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cargo.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dimensions: Mapped[float | None] = mapped_column(Numeric(12, 3))


class TrackingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tracking_events"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="TRANSPORT", index=True)
    location: Mapped[str | None] = mapped_column(Text)
    event_time_original: Mapped[str | None] = mapped_column(String(64))
    event_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    document_name: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW", index=True)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    change_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_REVIEW")


class DocumentChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_checklist_items"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    doc_type_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doc_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUIRED")
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id")
    )
    approval_role: Mapped[str | None] = mapped_column(String(64))


class DocumentAccessLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_access_logs"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class RevenueLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "revenue_lines"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    charge_code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1.0)
    unit_rate: Mapped[float | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ESTIMATED", index=True)
    is_additional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quotation_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )


class CostLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_lines"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), index=True
    )
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id"), index=True
    )
    charge_code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1.0)
    unit_rate: Mapped[float | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ESTIMATED", index=True)
    is_additional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quotation_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_lines.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )



class Invoice(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_invoice_number"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(64), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    exchange_rate_to_base: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=1.0)
    exchange_rate_source: Mapped[str | None] = mapped_column(String(64))
    subtotal_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)  # legacy compatibility
    tax_jurisdiction: Mapped[str | None] = mapped_column(String(64))
    tax_rate: Mapped[float | None] = mapped_column(Numeric(5, 4), default=0.0)
    tax_type: Mapped[str | None] = mapped_column(String(32))
    job_number: Mapped[str | None] = mapped_column(String(64))
    bl_awb_number: Mapped[str | None] = mapped_column(String(64))
    customer_po: Mapped[str | None] = mapped_column(String(64))
    quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id")
    )
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_APPROVAL")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    customer_email: Mapped[str | None] = mapped_column(String(255))
    payment_terms: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)


class InvoiceLine(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revenue_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("revenue_lines.id", ondelete="SET NULL"), index=True
    )
    charge_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=1.0)
    unit_rate: Mapped[float | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    source_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    exchange_rate: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=1.0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class CreditNote(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "credit_note_number", name="uq_credit_note_number"),
    )

    credit_note_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    credit_note_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ISSUED")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    financial_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id")
    )


class DebitNote(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "debit_notes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "debit_note_number", name="uq_debit_note_number"),
    )

    debit_note_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    charge_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    debit_note_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ISSUED")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    financial_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id")
    )


class Payable(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payables"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bill_number", name="uq_payable_bill_number"),
    )

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=True, index=True
    )
    bill_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bill_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    subtotal_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    paid_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED", index=True)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    variance_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    supporting_document_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    financial_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id")
    )


class PayableLine(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payable_lines"

    payable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payables.id"), nullable=False, index=True
    )
    cost_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_lines.id"), index=True
    )
    charge_code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1.0)
    unit_rate: Mapped[float | None] = mapped_column(Numeric(18, 4))
    expected_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    billed_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    variance_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0.0)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")


class PayablePayment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payable_payments"

    payable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payables.id"), nullable=False, index=True
    )
    payment_reference: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False, default="WIRE_TRANSFER")
    financial_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_entries.id")
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)


class EtaHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eta_history"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipment_legs.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(8), nullable=False)  # ETA or ETD
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    value: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShipmentException(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "shipment_exceptions"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False, index=True
    )
    exception_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="WARNING", index=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="OPERATIONAL", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    financial_impact_estimated: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)


