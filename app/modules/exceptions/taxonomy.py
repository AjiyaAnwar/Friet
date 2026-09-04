"""Exception Taxonomy and Configurable Registry (SRS Phase 4.7).

Configurable table/catalog of exception types, domains, and default severities.
Reuses and aligns with Phase 4.5 tracking event taxonomy.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExceptionTypeConfig:
    code: str
    name: str
    domain: str  # BOOKING, DOCUMENTATION, CUSTOMS, CARRIER, OPERATIONAL
    default_severity: str  # INFO, WARNING, CRITICAL
    description: str
    resolution_sla_hours: float = 24.0


# Configurable registry table (not a hardcoded enum with business logic)
DEFAULT_EXCEPTION_TAXONOMY: dict[str, ExceptionTypeConfig] = {
    "SHIPMENT_DELAY": ExceptionTypeConfig(
        code="SHIPMENT_DELAY",
        name="Shipment Transit Delay",
        domain="CARRIER",
        default_severity="WARNING",
        description="Carrier departure or transit schedule delay",
        resolution_sla_hours=12.0,
    ),
    "VESSEL_ROLL": ExceptionTypeConfig(
        code="VESSEL_ROLL",
        name="Vessel / Flight Roll",
        domain="CARRIER",
        default_severity="CRITICAL",
        description="Container or cargo rolled to next scheduled vessel/voyage",
        resolution_sla_hours=8.0,
    ),
    "CARGO_HOLD": ExceptionTypeConfig(
        code="CARGO_HOLD",
        name="Operational Cargo Hold",
        domain="OPERATIONAL",
        default_severity="WARNING",
        description="Operational hold placed on cargo at terminal or CFS",
        resolution_sla_hours=12.0,
    ),
    "CUSTOMS_HOLD": ExceptionTypeConfig(
        code="CUSTOMS_HOLD",
        name="Customs Regulatory Hold",
        domain="CUSTOMS",
        default_severity="CRITICAL",
        description="Customs authority inspection stop or documentation query",
        resolution_sla_hours=6.0,
    ),
    "MISSING_DOCUMENT": ExceptionTypeConfig(
        code="MISSING_DOCUMENT",
        name="Missing Mandatory Document",
        domain="DOCUMENTATION",
        default_severity="WARNING",
        description="Mandatory shipping or compliance document missing",
        resolution_sla_hours=8.0,
    ),
    "DGR_ISSUE": ExceptionTypeConfig(
        code="DGR_ISSUE",
        name="Dangerous Goods Non-Compliance",
        domain="DOCUMENTATION",
        default_severity="CRITICAL",
        description="Dangerous Goods packaging, labeling, or declaration mismatch",
        resolution_sla_hours=4.0,
    ),
    "CARGO_DAMAGE": ExceptionTypeConfig(
        code="CARGO_DAMAGE",
        name="Cargo Damage",
        domain="OPERATIONAL",
        default_severity="CRITICAL",
        description="Physical cargo damage noted during transit or handling",
        resolution_sla_hours=12.0,
    ),
    "CARGO_LOSS": ExceptionTypeConfig(
        code="CARGO_LOSS",
        name="Cargo Loss / Shortage",
        domain="OPERATIONAL",
        default_severity="CRITICAL",
        description="Total or partial cargo loss or pilferage",
        resolution_sla_hours=8.0,
    ),
    "SHORT_SHIPMENT": ExceptionTypeConfig(
        code="SHORT_SHIPMENT",
        name="Short Shipment Discrepancy",
        domain="OPERATIONAL",
        default_severity="WARNING",
        description="Discrepancy in package count vs manifest",
        resolution_sla_hours=12.0,
    ),
    "WRONG_DELIVERY": ExceptionTypeConfig(
        code="WRONG_DELIVERY",
        name="Misrouted / Wrong Delivery",
        domain="OPERATIONAL",
        default_severity="CRITICAL",
        description="Cargo delivered to incorrect consignee or facility",
        resolution_sla_hours=4.0,
    ),
    "RETURNED_TO_SHIPPER": ExceptionTypeConfig(
        code="RETURNED_TO_SHIPPER",
        name="Returned to Shipper",
        domain="BOOKING",
        default_severity="WARNING",
        description="Cargo refused at destination and returning to origin",
        resolution_sla_hours=24.0,
    ),
    "SECURITY_HOLD": ExceptionTypeConfig(
        code="SECURITY_HOLD",
        name="Security Authority Stop",
        domain="CUSTOMS",
        default_severity="CRITICAL",
        description="Cargo held by port, airport, or national security authorities",
        resolution_sla_hours=6.0,
    ),
    "WEATHER_DELAY": ExceptionTypeConfig(
        code="WEATHER_DELAY",
        name="Adverse Weather Delay",
        domain="CARRIER",
        default_severity="INFO",
        description="Transit delay due to adverse meteorological conditions",
        resolution_sla_hours=24.0,
    ),
    "EQUIPMENT_FAILURE": ExceptionTypeConfig(
        code="EQUIPMENT_FAILURE",
        name="Reefer / Equipment Failure",
        domain="CARRIER",
        default_severity="CRITICAL",
        description="Container reefer unit, genset, or equipment breakdown",
        resolution_sla_hours=4.0,
    ),
}

# Aliases for flexible input normalization
ALIASES: dict[str, str] = {
    "DELAY": "SHIPMENT_DELAY",
    "ROLL": "VESSEL_ROLL",
    "HOLD": "CARGO_HOLD",
    "DAMAGE": "CARGO_DAMAGE",
    "LOSS": "CARGO_LOSS",
    "RETURNED": "RETURNED_TO_SHIPPER",
}

VALID_DOMAINS = {"BOOKING", "DOCUMENTATION", "CUSTOMS", "CARRIER", "OPERATIONAL"}
VALID_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}
VALID_STATUSES = {"OPEN", "ACKNOWLEDGED", "UNDER_INVESTIGATION", "RESOLVED", "CLOSED"}


def resolve_exception_type(type_input: str) -> ExceptionTypeConfig | None:
    """Resolve and normalize an exception type code against the configurable taxonomy."""
    norm = type_input.strip().upper()
    resolved_code = ALIASES.get(norm, norm)
    return DEFAULT_EXCEPTION_TAXONOMY.get(resolved_code)

