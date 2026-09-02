"""
FreightCore Commercial Domain Entities (Team 2).

Directly aligned with freightcore_unified_erd.html (Diagrams 1, 2, 3, 4).
These domain models are decoupled from any ORM and represent pure business state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from enum import Enum
import uuid


def generate_uuid() -> str:
    return str(uuid.uuid4())


# =====================================================================
# Diagram 1: Master & Reference Data Entities
# =====================================================================

@dataclass
class Country:
    iso_code: str  # CHAR(2), e.g. "PK", "AE", "SA", "US"
    name: str
    region: str = ""
    trade_zone: str = ""
    is_sanctioned: bool = False
    requires_permit: bool = False
    id: str = field(default_factory=generate_uuid)


@dataclass
class Location:
    name: str
    country_id: str | None = None
    city: str = ""
    type: str = ""
    un_locode: str | None = None
    iata_code: str | None = None
    timezone: str = "UTC"
    is_active: bool = True
    id: str = field(default_factory=generate_uuid)


@dataclass
class Zone:
    zone_code: str
    name: str
    country_id: str
    id: str = field(default_factory=generate_uuid)


@dataclass
class Currency:
    code: str  # e.g. "USD", "PKR", "SAR", "EUR"
    name: str
    symbol: str = ""


@dataclass
class ExchangeRate:
    currency_code: str
    rate_date: date
    rate_to_base: float  # e.g. 1 USD = X base
    source: str = "CENTRAL_BANK"
    id: str = field(default_factory=generate_uuid)


@dataclass
class Incoterm:
    code: str  # e.g. "FOB", "CIF", "EXW", "DDP", "DAP"
    name: str


@dataclass
class ContainerType:
    code: str  # e.g. "20GP", "40GP", "40HC", "20RF", "40RF"
    cbm_capacity: float
    max_payload_kg: float


@dataclass
class Commodity:
    hs_code: str
    name: str
    is_dgr: bool = False
    export_restricted: bool = False
    import_restricted: bool = False
    id: str = field(default_factory=generate_uuid)


@dataclass
class PackageType:
    code: str  # e.g. "CTN", "PLT", "DRM", "BAG", "BDL"
    name: str


@dataclass
class UldType:
    code: str  # e.g. "PMC", "AKE"
    name: str
    volume_cbm: float


@dataclass
class ChargeCode:
    code: str  # e.g. "OFT", "AFT", "BAF", "FSC", "THC_O", "THC_D", "DOC"
    name: str
    charge_type: str = "FREIGHT"  # "FREIGHT", "SURCHARGE", "LOCAL", "AGENT"
    rate_basis: str = "FLAT"  # "PER_KG", "PER_CBM", "PER_CONTAINER", "FLAT", "PERCENTAGE"
    applicable_mode: str = "ALL"  # "SEA", "AIR", "ALL"


@dataclass
class DocumentType:
    code: str  # e.g. "MBL", "HBL", "MAWB", "HAWB", "COMMERCIAL_INVOICE", "PACKING_LIST", "COO"
    name: str
    applicable_mode: str = "ALL"


@dataclass
class Carrier:
    carrier_type: str  # "SHIPPING_LINE", "AIRLINE"
    name: str
    scac_code: str | None = None
    iata_code: str | None = None
    iata_prefix: str | None = None
    is_nvocc: bool = False
    hub_locations: str = ""
    id: str = field(default_factory=generate_uuid)


@dataclass
class Vessel:
    imo_number: str
    name: str
    flag: str
    owner_carrier_id: str
    teu_capacity: int
    vessel_type: str = "CONTAINER"
    id: str = field(default_factory=generate_uuid)


@dataclass
class VesselSchedule:
    carrier_id: str
    service_name: str
    vessel_id: str
    voyage_number: str
    port_rotation: list[dict] = field(default_factory=list)  # [{"port": "PKKAR", "eta": ..., "etd": ...}]
    cy_cutoff: datetime | None = None
    si_cutoff: datetime | None = None
    vgm_cutoff: datetime | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class FlightSchedule:
    carrier_id: str
    origin_location_id: str
    destination_location_id: str
    flight_number: str
    frequency: str = "1234567"  # Days of week
    sched_departure: time | None = None
    sched_arrival: time | None = None
    cargo_cutoff: str | None = None
    doc_cutoff: str | None = None
    id: str = field(default_factory=generate_uuid)


# =====================================================================
# Diagram 2: Customer, Vendor, Agent & Credit
# =====================================================================

class CreditTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    NEW = "NEW"
    BLOCKED = "BLOCKED"


@dataclass
class Customer:
    customer_code: str
    name: str
    credit_limit_amount: float
    credit_limit_currency: str = "USD"
    payment_terms_days: int = 30
    credit_tier: CreditTier = CreditTier.NEW
    tenant_id: str = "default_tenant"
    tax_registration: str = ""
    registration_number: str = ""
    iata_fiata_membership: str = ""
    preferred_carrier_ids: list[str] = field(default_factory=list)
    preferred_lanes: list[dict] = field(default_factory=list)
    kyc_status: str = "VERIFIED"
    is_active: bool = True
    onboarding_date: date = field(default_factory=date.today)
    id: str = field(default_factory=generate_uuid)


@dataclass
class CustomerContact:
    customer_id: str
    name: str
    role: str
    email: str = ""
    phone: str = ""
    id: str = field(default_factory=generate_uuid)


@dataclass
class CustomerAddress:
    customer_id: str
    address_type: str  # "REGISTERED", "BILLING", "OPERATIONAL"
    line1: str
    city: str
    country: str
    id: str = field(default_factory=generate_uuid)


@dataclass
class CustomerPortalUser:
    customer_id: str
    user_id: str
    id: str = field(default_factory=generate_uuid)


@dataclass
class CustomerCreditOverride:
    customer_id: str
    reason: str
    approved_by: str
    valid_from: date
    valid_to: date
    id: str = field(default_factory=generate_uuid)


@dataclass
class Vendor:
    vendor_code: str
    name: str
    vendor_type: str  # "SHIPPING_LINE", "AIRLINE", "TRUCKING", "CFS_OPERATOR", "AGENT", etc.
    tax_registration: str = ""
    bank_details: dict = field(default_factory=dict)
    payment_terms: str = "30_DAYS"
    performance_score: float = 100.0
    id: str = field(default_factory=generate_uuid)


@dataclass
class Agent:
    vendor_id: str
    coverage_country: str
    coverage_city: str
    services_provided: str = ""
    certifications: str = ""
    settlement_model: str = "INVOICE"  # "INVOICE", "COMMISSION", "NETTING"
    id: str = field(default_factory=generate_uuid)


@dataclass
class AgentRateAgreement:
    agent_id: str
    rate_id: str
    effective_date: date
    expiry_date: date
    id: str = field(default_factory=generate_uuid)


# =====================================================================
# Diagram 3: Rate / Tariff Engine Entities
# =====================================================================

class RateCategory(str, Enum):
    CONTRACT_NAC = "CONTRACT_NAC"
    SPOT = "SPOT"
    LANE_NAC = "LANE_NAC"
    PROMOTIONAL = "PROMOTIONAL"
    FAK = "FAK"
    AGENT = "AGENT"


class RateStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


class RateVersionApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"


@dataclass
class RateLine:
    charge_code: str  # FK -> ChargeCode.code (e.g. "OFT", "AFT")
    rate_basis: str  # "PER_KG", "PER_CBM", "PER_CONTAINER", "FLAT", "WEIGHT_BREAK"
    amount: float
    weight_break_from: float | None = None  # e.g. 45, 100, 250, 500, 1000
    weight_break_to: float | None = None
    container_type_code: str | None = None  # FK -> ContainerType.code (e.g. "20GP", "40HC")
    rate_version_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RateSurcharge:
    charge_code: str  # FK -> ChargeCode.code (e.g. "BAF", "FSC", "THC_O")
    basis: str  # "PER_TEU", "PERCENTAGE", "FLAT", "PER_KG", "PER_CBM"
    amount: float
    applicable_from: date
    applicable_to: date
    rate_version_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RateVersion:
    rate_id: str
    version_number: int = 1
    modified_by: str = "SYSTEM"
    modified_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = "Initial version"
    approval_status: RateVersionApprovalStatus = RateVersionApprovalStatus.APPROVED
    lines: list[RateLine] = field(default_factory=list)
    surcharges: list[RateSurcharge] = field(default_factory=list)
    id: str = field(default_factory=generate_uuid)


@dataclass
class Rate:
    rate_number: str
    rate_type: str  # "SEA", "AIR", "LAND"
    rate_category: RateCategory
    carrier_vendor_id: str  # FK -> Vendor.id or Carrier.id
    service_name: str
    origin_location_id: str  # FK -> Location.id
    destination_location_id: str  # FK -> Location.id
    effective_date: date
    expiry_date: date
    currency_code: str = "USD"
    status: RateStatus = RateStatus.ACTIVE
    via_routing: str = ""
    commodity_id: str | None = None
    customer_id: str | None = None  # FK -> Customer.id (for CONTRACT_NAC or SPOT)
    versions: list[RateVersion] = field(default_factory=list)
    id: str = field(default_factory=generate_uuid)

    @property
    def current_version(self) -> RateVersion | None:
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)


@dataclass
class MarginRule:
    service_type: str  # "SEA_FCL", "SEA_LCL", "AIR", "*"
    min_margin_pct: float | None = None
    min_margin_amount: float | None = None
    customer_tier_overrides: dict[str, float] = field(default_factory=dict)  # {"A": 3.0, "B": 5.0}
    lane_overrides: dict[str, float] = field(default_factory=dict)  # {"PKKAR-AEJEA": 4.0}
    id: str = field(default_factory=generate_uuid)


# =====================================================================
# Diagram 4: Commercial Core (RFQ, Route, Quotation, Job)
# =====================================================================

class RfqMode(str, Enum):
    SEA = "SEA"
    AIR = "AIR"


class RfqServiceType(str, Enum):
    FCL = "FCL"
    LCL = "LCL"
    DIRECT = "DIRECT"
    CONSOL = "CONSOL"


class RfqStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PRICING_IN_PROGRESS = "PRICING_IN_PROGRESS"
    QUOTED = "QUOTED"
    SENT_TO_CUSTOMER = "SENT_TO_CUSTOMER"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"


class PartyRole(str, Enum):
    SHIPPER = "SHIPPER"
    CONSIGNEE = "CONSIGNEE"
    NOTIFY_1 = "NOTIFY_1"
    NOTIFY_2 = "NOTIFY_2"
    NOTIFY_3 = "NOTIFY_3"
    BUYER = "BUYER"


@dataclass
class RfqParty:
    party_role: PartyRole
    name: str
    address: str = ""
    contact: str = ""
    rfq_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RfqCargoLine:
    packages: int
    gross_weight: float
    commodity_id: str | None = None
    package_type_code: str = "CTN"
    net_weight: float | None = None
    volume_cbm: float = 0.0
    dimensions_length_cm: float | None = None
    dimensions_width_cm: float | None = None
    dimensions_height_cm: float | None = None
    cargo_value: float | None = None
    currency_code: str = "USD"
    is_stackable: bool = True
    is_tiltable: bool = False
    rfq_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RfqContainerRequirement:
    container_type_code: str  # "20GP", "40GP", "40HC", "20RF", "40RF"
    qty: int = 1
    weight_per_container: float = 0.0
    temperature_controlled: bool = False
    genset_required: bool = False
    soc_coc: str = "COC"  # "SOC" (Shipper Owned) or "COC" (Carrier Owned)
    oog_dimensions: dict = field(default_factory=dict)
    rfq_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RfqSpecialRequirement:
    dgr_flag: bool = False
    dgr_un_number: str | None = None
    dgr_class: str | None = None
    temp_controlled: bool = False
    insurance: bool = False
    fumigation: bool = False
    inspection: bool = False
    special_handling_codes: str = ""
    customs_docs_required: str = ""
    lc_flag: bool = False
    lc_number: str | None = None
    rfq_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class Rfq:
    rfq_number: str
    customer_id: str
    origin_location_id: str
    destination_location_id: str
    mode: RfqMode
    service_type: RfqServiceType
    cargo_ready_date: date
    preferred_departure: date
    required_delivery: date
    incoterm_code: str = "FOB"
    movement_type: str = "P2P"  # "D2D", "P2P", "D2P", "P2D", "A2A"
    preferred_carrier_id: str | None = None
    priority: str = "STANDARD"  # "STANDARD", "URGENT"
    status: RfqStatus = RfqStatus.DRAFT
    assigned_to: str | None = None  # FK -> User.id (Pricing Analyst)
    parties: list[RfqParty] = field(default_factory=list)
    cargo_lines: list[RfqCargoLine] = field(default_factory=list)
    container_requirements: list[RfqContainerRequirement] = field(default_factory=list)
    special_requirement: RfqSpecialRequirement | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class RouteLeg:
    from_location_id: str
    to_location_id: str
    carrier_id: str
    sequence: int = 1
    vessel_id: str | None = None
    flight_id: str | None = None
    etd: datetime | None = None
    eta: datetime | None = None
    transit_time_hours: float = 0.0
    is_transshipment: bool = False
    route_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class Route:
    origin_location_id: str
    destination_location_id: str
    mode: str  # "SEA", "AIR"
    legs: list[RouteLeg] = field(default_factory=list)
    id: str = field(default_factory=generate_uuid)

    @property
    def total_transit_hours(self) -> float:
        return sum(leg.transit_time_hours for leg in self.legs)

    @property
    def transshipment_count(self) -> int:
        return max(len(self.legs) - 1, 0)

    @property
    def carriers_used(self) -> set[str]:
        return {leg.carrier_id for leg in self.legs}


class ChargeCategory(str, Enum):
    FREIGHT = "FREIGHT"
    SURCHARGE = "SURCHARGE"
    LOCAL = "LOCAL"
    AGENT = "AGENT"


@dataclass
class QuotationLine:
    charge_code: str  # FK -> ChargeCode.code (e.g. "OFT", "BAF", "THC_D")
    category: ChargeCategory
    cost_amount: float
    sell_amount: float
    description: str = ""
    rate_version_id: str | None = None
    quotation_option_id: str | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class QuotationOption:
    label: str  # e.g. "Option A - Fastest", "Option B - Cheapest"
    charge_lines: list[QuotationLine] = field(default_factory=list)
    route_id: str | None = None
    primary_rate_version_id: str | None = None
    currency_code: str = "USD"
    is_below_margin: bool = False
    quotation_id: str | None = None
    id: str = field(default_factory=generate_uuid)

    @property
    def total_cost(self) -> float:
        return round(sum(c.cost_amount for c in self.charge_lines), 2)

    @property
    def total_sell(self) -> float:
        return round(sum(c.sell_amount for c in self.charge_lines), 2)

    @property
    def gross_margin(self) -> float:
        return round(self.total_sell - self.total_cost, 2)

    @property
    def margin_pct(self) -> float:
        if self.total_sell == 0:
            return 0.0
        return round((self.gross_margin / self.total_sell) * 100, 2)


class QuotationStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT_TO_CUSTOMER = "SENT_TO_CUSTOMER"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"


@dataclass
class QuotationApproval:
    quotation_id: str
    approval_type: str  # "BELOW_MARGIN", "HIGH_VALUE", "HIGH_RISK_CUSTOMER", "DGR_COMPLIANCE", "MANUAL_OVERRIDE"
    approver_role: str  # "PRICING_MANAGER", "FINANCE_CONTROLLER", "COMPLIANCE_DGR"
    status: str = "PENDING"  # "PENDING", "APPROVED", "REJECTED"
    approved_by: str | None = None
    approved_at: datetime | None = None
    id: str = field(default_factory=generate_uuid)


@dataclass
class Quotation:
    quotation_number: str
    rfq_id: str
    expiry_date: date
    status: QuotationStatus = QuotationStatus.DRAFT
    parent_quotation_id: str | None = None  # Self-reference for revision chaining
    sent_at: datetime | None = None
    options: list[QuotationOption] = field(default_factory=list)
    approvals: list[QuotationApproval] = field(default_factory=list)
    id: str = field(default_factory=generate_uuid)


@dataclass
class Job:
    job_number: str  # Format: "{Branch}-{Mode}-{Direction}-{YY}{MM}-{Seq}"
    quotation_id: str
    customer_id: str
    status: str = "CONFIRMED"
    id: str = field(default_factory=generate_uuid)
