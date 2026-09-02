"""Analytics data warehouse star-schema models (reporting replica)."""

import uuid
from datetime import date

from sqlalchemy import Date, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class DimTime(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dim_time"

    date_key: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)


class DimCustomer(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dim_customers"

    source_customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    credit_tier: Mapped[str | None] = mapped_column(String(16))


class DimCarrier(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dim_carriers"

    source_carrier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    carrier_type: Mapped[str | None] = mapped_column(String(32))


class DimRoute(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dim_routes"

    source_route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)


class FactShipment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fact_shipments"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_dim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    route_dim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    time_dim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class FactFinancialEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fact_financial_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    time_dim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    debit_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    credit_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactTrackingEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "fact_tracking_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    shipment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    time_dim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
