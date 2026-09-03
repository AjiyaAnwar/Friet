"""
Master Data models - field-for-field from freightcore_unified_erd.html
(source1 and source2 blocks). These are plain dataclasses; persistence
is handled entirely through ports.py repositories, never here.
"""

from dataclasses import dataclass, field
from datetime import date


# --- Geographic reference (source1) ---

@dataclass
class Country:
    id: str
    iso_code: str
    name: str
    region: str
    trade_zone: str
    is_sanctioned: bool = False
    requires_permit: bool = False


@dataclass
class Location:
    id: str
    un_locode: str
    iata_code: str | None
    name: str
    country_id: str
    city: str
    type: str
    timezone: str
    is_active: bool = True


@dataclass
class Zone:
    id: str
    zone_code: str
    name: str
    country_id: str


# --- Currency & FX (source1) ---

@dataclass
class Currency:
    code: str
    name: str
    symbol: str


@dataclass
class ExchangeRate:
    id: str
    currency_code: str
    rate_date: date
    rate_to_base: float
    source: str


# --- Simple coded reference tables (source1) ---

@dataclass
class Incoterm:
    code: str
    name: str


@dataclass
class ContainerType:
    code: str
    cbm_capacity: float
    max_payload_kg: float


@dataclass
class Commodity:
    id: str
    hs_code: str
    name: str
    is_dgr: bool = False
    export_restricted: bool = False
    import_restricted: bool = False


@dataclass
class PackageType:
    code: str
    name: str


@dataclass
class ULDType:
    code: str
    name: str
    volume_cbm: float


@dataclass
class ChargeCode:
    code: str
    name: str
    charge_type: str
    rate_basis: str
    applicable_mode: str


@dataclass
class DocumentType:
    code: str
    name: str
    applicable_mode: str


# --- Carrier & Network (source1) ---

@dataclass
class Carrier:
    id: str
    carrier_type: str
    scac_code: str | None
    iata_code: str | None
    iata_prefix: str | None
    name: str
    is_nvocc: bool = False
    hub_locations: str = ""


@dataclass
class Vessel:
    id: str
    imo_number: str
    name: str
    flag: str
    owner_carrier_id: str
    teu_capacity: int
    vessel_type: str


@dataclass
class VesselSchedule:
    id: str
    carrier_id: str
    service_name: str
    vessel_id: str
    voyage_number: str
    port_rotation: list
    cy_cutoff: str
    si_cutoff: str
    vgm_cutoff: str


@dataclass
class FlightSchedule:
    id: str
    carrier_id: str
    origin_location_id: str
    destination_location_id: str
    flight_number: str
    frequency: str
    sched_departure: str
    sched_arrival: str
    cargo_cutoff: str
    doc_cutoff: str


# --- Customer / Vendor / Agent (source2) ---

@dataclass
class Customer:
    id: str
    tenant_id: str
    customer_code: str
    name: str
    tax_registration: str
    registration_number: str
    iata_fiata_membership: str | None
    credit_limit_amount: float
    credit_limit_currency: str
    payment_terms_days: int
    credit_tier: str
    kyc_status: str
    is_active: bool = True
    onboarding_date: date | None = None
    preferred_carrier_ids: list = field(default_factory=list)
    preferred_lanes: list = field(default_factory=list)


@dataclass
class CustomerContact:
    id: str
    customer_id: str
    name: str
    role: str
    email: str
    phone: str


@dataclass
class CustomerAddress:
    id: str
    customer_id: str
    address_type: str
    line1: str
    city: str
    country: str


@dataclass
class CustomerPortalUser:
    id: str
    customer_id: str
    user_id: str


@dataclass
class CustomerCreditOverride:
    id: str
    customer_id: str
    reason: str
    approved_by: str
    valid_from: date
    valid_to: date


@dataclass
class Vendor:
    id: str
    vendor_code: str
    name: str
    vendor_type: str
    tax_registration: str
    bank_details: dict
    payment_terms: str
    performance_score: float | None = None


@dataclass
class Agent:
    id: str
    vendor_id: str
    coverage_country: str
    coverage_city: str
    services_provided: str
    certifications: str
    settlement_model: str


@dataclass
class AgentRateAgreement:
    id: str
    agent_id: str
    rate_id: str
    effective_date: date
    expiry_date: date
