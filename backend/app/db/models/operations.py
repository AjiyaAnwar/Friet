"""Additional operations models for air, sea, exceptions, and notifications."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
    Boolean,
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

class IdempotencyRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)


class DeadLetterRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dead_letter_records"
    
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AWBRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "awb_records"
    
    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False)
    awb_type: Mapped[str] = mapped_column(String(10), nullable=False)  # HAWB or MAWB
    parent_mawb_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("awb_records.id"), nullable=True)
    airline_prefix: Mapped[str] = mapped_column(String(3), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")


class SeaShipmentDetail(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sea_shipment_details"
    
    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shipments.id"), nullable=False)
    mbl_number: Mapped[str | None] = mapped_column(String(64))
    hbl_number: Mapped[str | None] = mapped_column(String(64))
    vessel_name: Mapped[str | None] = mapped_column(String(128))
    voyage_number: Mapped[str | None] = mapped_column(String(64))




class ULDAssignment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "uld_assignments"
    
    uld_number: Mapped[str] = mapped_column(String(32), nullable=False)
    flight_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("flight_schedules.id"), nullable=False)
    awb_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("awb_records.id"), nullable=False)
    pieces: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)


class NotificationEvent(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "notification_events"
    
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
