"""Commercial domain models: customers, rates, RFQ, quotation, job."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import (
    AuditActorMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Customer(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("tenant_id", "customer_code", name="uq_customer_code"),)

    customer_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    tax_registration_encrypted: Mapped[str | None] = mapped_column(Text)
    registration_number: Mapped[str | None] = mapped_column(Text)
    iata_fiata_membership: Mapped[str | None] = mapped_column(Text)
    credit_limit_amount_encrypted: Mapped[str | None] = mapped_column(Text)
    credit_limit_currency: Mapped[str | None] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    credit_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    preferred_lanes: Mapped[dict | None] = mapped_column(JSONB)
    preferred_service_types: Mapped[dict | None] = mapped_column(JSONB)
    kyc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    onboarding_date: Mapped[date | None] = mapped_column(Date)


class CustomerContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_contacts"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(Text)
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    email_lookup_hash: Mapped[str | None] = mapped_column(String(64))
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    phone_lookup_hash: Mapped[str | None] = mapped_column(String(64))


class CustomerAddress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_addresses"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    address_type: Mapped[str] = mapped_column(String(32), nullable=False)
    line1: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str | None] = mapped_column(Text)
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False
    )


class CustomerPortalUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_portal_users"
    __table_args__ = (UniqueConstraint("customer_id", "user_id", name="uq_customer_portal_user"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class CustomerCreditOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_credit_overrides"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)


class Vendor(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("tenant_id", "vendor_code", name="uq_vendor_code"),)

    vendor_code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_registration_encrypted: Mapped[str | None] = mapped_column(Text)
    bank_details_encrypted: Mapped[str | None] = mapped_column(Text)
    payment_terms: Mapped[int | None] = mapped_column(Integer)
    performance_score: Mapped[float | None] = mapped_column(Numeric(5, 2))


class Agent(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "agents"

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id")
    )
    coverage_country_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id")
    )
    coverage_city: Mapped[str | None] = mapped_column(Text)
    services_provided: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    certifications: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    settlement_model: Mapped[str] = mapped_column(String(32), nullable=False, default="INVOICE")


class AgentRateAgreement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_rate_agreements"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    rate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rates.id"), nullable=False
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)


class Rate(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "rates"
    __table_args__ = (UniqueConstraint("tenant_id", "rate_number", name="uq_rate_number"),)

    rate_number: Mapped[str] = mapped_column(Text, nullable=False)
    rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_category: Mapped[str] = mapped_column(String(32), nullable=False)
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("carriers.id"))
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vendors.id"))
    service_name: Mapped[str | None] = mapped_column(Text)
    origin_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    via_routing: Mapped[str | None] = mapped_column(Text)
    commodity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commodities.id")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id")
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")


class RateVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rate_versions"
    __table_args__ = (UniqueConstraint("rate_id", "version_number", name="uq_rate_version"),)

    rate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rates.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    modified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    modified_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")


class RateLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rate_lines"

    rate_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id"), nullable=False
    )
    charge_code: Mapped[str] = mapped_column(Text, ForeignKey("charge_codes.code"))
    rate_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    weight_break_from: Mapped[float | None] = mapped_column(Numeric(12, 3))
    weight_break_to: Mapped[float | None] = mapped_column(Numeric(12, 3))
    container_type_code: Mapped[str | None] = mapped_column(Text, ForeignKey("container_types.code"))
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class RateSurcharge(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rate_surcharges"

    rate_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id"), nullable=False
    )
    charge_code: Mapped[str] = mapped_column(Text, ForeignKey("charge_codes.code"))
    basis: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    applicable_from: Mapped[date | None] = mapped_column(Date)
    applicable_to: Mapped[date | None] = mapped_column(Date)


class RFQ(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "rfqs"
    __table_args__ = (UniqueConstraint("tenant_id", "rfq_number", name="uq_rfq_number"),)

    rfq_number: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    origin_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(32))
    incoterm_code: Mapped[str | None] = mapped_column(Text, ForeignKey("incoterms.code"))
    movement_type: Mapped[str | None] = mapped_column(String(32))
    cargo_ready_date: Mapped[date | None] = mapped_column(Date)
    preferred_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    required_delivery: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferred_carrier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id")
    )
    priority: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class RFQParty(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rfq_parties"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False
    )
    party_role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address_encrypted: Mapped[str | None] = mapped_column(Text)
    contact_encrypted: Mapped[str | None] = mapped_column(Text)


class RFQCargoLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rfq_cargo_lines"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commodities.id")
    )
    package_type_code: Mapped[str | None] = mapped_column(Text, ForeignKey("package_types.code"))
    packages: Mapped[int | None] = mapped_column(Integer)
    gross_weight_kg: Mapped[float | None] = mapped_column(Numeric(12, 3))
    net_weight_kg: Mapped[float | None] = mapped_column(Numeric(12, 3))
    volume_cbm: Mapped[float | None] = mapped_column(Numeric(12, 3))
    length_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    width_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    height_cm: Mapped[float | None] = mapped_column(Numeric(10, 2))
    cargo_value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    currency_code: Mapped[str | None] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    is_stackable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_tiltable: Mapped[bool] = mapped_column(Boolean, default=False)


class RFQContainerRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rfq_container_requirements"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False
    )
    container_type_code: Mapped[str] = mapped_column(Text, ForeignKey("container_types.code"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_per_container_kg: Mapped[float | None] = mapped_column(Numeric(12, 3))
    temperature: Mapped[float | None] = mapped_column(Numeric(6, 2))
    temperature_unit: Mapped[str | None] = mapped_column(String(8))
    genset_required: Mapped[bool] = mapped_column(Boolean, default=False)
    soc_coc: Mapped[str | None] = mapped_column(String(8))
    oog_dimensions: Mapped[dict | None] = mapped_column(JSONB)


class RFQSpecialRequirement(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rfq_special_requirements"

    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False, unique=True
    )
    dgr_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature_details: Mapped[dict | None] = mapped_column(JSONB)
    insurance_required: Mapped[bool] = mapped_column(Boolean, default=False)
    insurance_details: Mapped[dict | None] = mapped_column(JSONB)
    fumigation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=False)
    special_handling_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    customs_docs_required: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    lc_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    lc_number: Mapped[str | None] = mapped_column(Text)


class Route(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "routes"

    origin_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(8), nullable=False)


class RouteLeg(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "route_legs"
    __table_args__ = (UniqueConstraint("route_id", "sequence", name="uq_route_leg_sequence"),)

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routes.id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    carrier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carriers.id")
    )
    vessel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vessels.id"))
    flight_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flight_schedules.id")
    )
    etd: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transit_time_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    is_transshipment: Mapped[bool] = mapped_column(Boolean, default=False)


class Quotation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "quotations"
    __table_args__ = (UniqueConstraint("tenant_id", "quotation_number", name="uq_quotation_number"),)

    quotation_number: Mapped[str] = mapped_column(Text, nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rfqs.id"), nullable=False
    )
    parent_quotation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    expiry_date: Mapped[date | None] = mapped_column(Date)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 4))


class QuotationOption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quotation_options"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    route_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("routes.id"))
    primary_rate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id")
    )
    total_cost: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    total_sell: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    gross_margin: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    margin_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    currency_code: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    is_below_margin: Mapped[bool] = mapped_column(Boolean, default=False)


class QuotationLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quotation_lines"

    quotation_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotation_options.id"), nullable=False
    )
    charge_code: Mapped[str] = mapped_column(Text, ForeignKey("charge_codes.code"))
    category: Mapped[str | None] = mapped_column(Text)
    rate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_versions.id")
    )
    cost_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    sell_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class QuotationApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quotation_approvals"

    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False
    )
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False)
    approver_role: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "job_number", name="uq_job_number"),)

    job_number: Mapped[str] = mapped_column(Text, nullable=False)
    quotation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotations.id"), nullable=False, unique=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")


class JobTask(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    """Initial operational tasks created atomically with an accepted quote."""

    __tablename__ = "job_tasks"

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True
    )
    department: Mapped[str] = mapped_column(String(32), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
