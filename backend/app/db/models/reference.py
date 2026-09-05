"""Master and reference data models."""

import uuid
from datetime import date

from sqlalchemy import (
    CHAR,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Country(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "countries"

    iso_code: Mapped[str] = mapped_column(CHAR(2), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text)
    trade_zone: Mapped[str | None] = mapped_column(Text)
    is_sanctioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_permit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "locations"

    un_locode: Mapped[str | None] = mapped_column(Text, unique=True)
    iata_code: Mapped[str | None] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False
    )
    city: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    timezone: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Zone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "zones"

    zone_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False
    )
    cities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(Text)


class ExchangeRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("currency_code", "rate_date", "source", name="uq_exchange_rate"),
    )

    currency_code: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate_to_base: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)


class Incoterm(Base):
    __tablename__ = "incoterms"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class ContainerType(Base):
    __tablename__ = "container_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    cbm_capacity: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    max_payload_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)


class Commodity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commodities"

    hs_code: Mapped[str] = mapped_column(CHAR(6), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_dgr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    export_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    import_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PackageType(Base):
    __tablename__ = "package_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class UldType(Base):
    __tablename__ = "uld_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    volume_cbm: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)


class ChargeCode(Base):
    __tablename__ = "charge_codes"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    charge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    applicable_mode: Mapped[str] = mapped_column(String(8), nullable=False)


class DocumentTypeRef(Base):
    __tablename__ = "document_types"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    applicable_mode: Mapped[str] = mapped_column(String(8), nullable=False)


class Carrier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "carriers"

    carrier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scac_code: Mapped[str | None] = mapped_column(Text)
    iata_code: Mapped[str | None] = mapped_column(CHAR(2))
    iata_prefix: Mapped[str | None] = mapped_column(CHAR(3))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_nvocc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hub_locations: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class Vessel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vessels"

    imo_number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    flag: Mapped[str | None] = mapped_column(Text)
    owner_carrier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=False
    )
    teu_capacity: Mapped[int | None] = mapped_column(Integer)
    vessel_type: Mapped[str | None] = mapped_column(Text)


class VesselSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vessel_schedules"

    carrier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=False
    )
    service_name: Mapped[str] = mapped_column(Text, nullable=False)
    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vessels.id"), nullable=False
    )
    voyage_number: Mapped[str] = mapped_column(Text, nullable=False)
    port_rotation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    cy_cutoff: Mapped[date | None] = mapped_column(Date)
    si_cutoff: Mapped[date | None] = mapped_column(Date)
    vgm_cutoff: Mapped[date | None] = mapped_column(Date)


class FlightSchedule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "flight_schedules"

    carrier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id"), nullable=False
    )
    origin_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    flight_number: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    scheduled_departure: Mapped[str | None] = mapped_column(Text)
    scheduled_arrival: Mapped[str | None] = mapped_column(Text)
    cargo_cutoff: Mapped[str | None] = mapped_column(Text)
    documentation_cutoff: Mapped[str | None] = mapped_column(Text)
