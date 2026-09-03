"""
Rate/Tariff Engine models - field-for-field from freightcore_unified_erd.html
(source3 block): RATE, RATE_VERSION, RATE_LINE, RATE_SURCHARGE, MARGIN_RULE.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Rate:
    id: str
    rate_number: str
    rate_type: str
    rate_category: str
    carrier_vendor_id: str
    service_name: str
    origin_location_id: str
    destination_location_id: str
    via_routing: str | None
    commodity_id: str | None
    customer_id: str | None
    effective_date: date
    expiry_date: date
    currency_code: str
    status: str


@dataclass
class RateVersion:
    id: str
    rate_id: str
    version_number: int
    modified_by: str
    modified_date: datetime
    reason: str
    approval_status: str


@dataclass
class RateLine:
    id: str
    rate_version_id: str
    charge_code: str
    rate_basis: str
    weight_break_from: float | None
    weight_break_to: float | None
    container_type_code: str | None
    amount: float


@dataclass
class RateSurcharge:
    id: str
    rate_version_id: str
    charge_code: str
    basis: str
    amount: float
    applicable_from: date
    applicable_to: date


@dataclass
class MarginRule:
    id: str
    service_type: str
    min_margin_pct: float | None
    min_margin_amount: float | None
    customer_tier_overrides: dict = field(default_factory=dict)
    lane_overrides: dict = field(default_factory=dict)
