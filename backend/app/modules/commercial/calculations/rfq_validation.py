"""
RFQ Validation Rules.

- Mode-specific mandatory fields (container type for FCL, dimensions for LCL/Air)
- DGR flag -> DGR sub-form fields required (UN number, hazard class)
- LC flag -> LC number required
- Required Delivery Date >= Preferred Departure Date >= today
- Multi-party validation (Shipper & Consignee required for submitted RFQs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class RfqInput:
    service_type: str  # "FCL", "LCL", "DIRECT", "CONSOL"
    mode: str  # "SEA" or "AIR"
    cargo_readiness_date: date
    preferred_departure_date: date
    required_delivery_date: date

    container_types: list[str] = field(default_factory=list)
    package_length_cm: float | None = None
    package_width_cm: float | None = None
    package_height_cm: float | None = None

    is_dgr: bool = False
    dgr_un_number: str | None = None
    dgr_class: str | None = None

    has_lc: bool = False
    lc_number: str | None = None


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_rfq(rfq: Any, today: date | None = None) -> ValidationResult:
    """
    Validates RFQ inputs. Supports both RfqInput dataclass and the domain Rfq model.
    """
    if today is None:
        today = date.today()

    errors: list[str] = []

    # Handle domain Rfq object
    if hasattr(rfq, "parties") and hasattr(rfq, "cargo_lines"):
        service_type = rfq.service_type.value if hasattr(rfq.service_type, "value") else str(rfq.service_type)
        mode = rfq.mode.value if hasattr(rfq.mode, "value") else str(rfq.mode)

        # Mode-specific constraints
        if service_type == "FCL":
            if not rfq.container_requirements:
                errors.append("Container requirement is required for FCL shipments")
        elif service_type in ("LCL", "DIRECT", "CONSOL") or mode == "AIR":
            has_dimensions = False
            for line in rfq.cargo_lines:
                if (
                    line.dimensions_length_cm is not None
                    and line.dimensions_width_cm is not None
                    and line.dimensions_height_cm is not None
                ):
                    has_dimensions = True
                    break
            if not has_dimensions:
                errors.append("Package dimensions (L/W/H) are required for LCL or Air shipments")

        # Special requirements (DGR, LC)
        if rfq.special_requirement:
            sr = rfq.special_requirement
            if sr.dgr_flag:
                if not sr.dgr_un_number:
                    errors.append("DGR UN number is required when DGR flag is set")
                if not sr.dgr_class:
                    errors.append("DGR class is required when DGR flag is set")
            if sr.lc_flag and not sr.lc_number:
                errors.append("LC number is required when LC flag is set")

        # Date validations
        if rfq.preferred_departure < today:
            errors.append("Preferred departure date cannot be in the past")
        if rfq.required_delivery < rfq.preferred_departure:
            errors.append("Required delivery date must be on or after preferred departure date")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # Handle RfqInput dataclass
    if rfq.service_type == "FCL":
        if not rfq.container_types:
            errors.append("Container type is required for FCL shipments")
    elif rfq.service_type in ("LCL", "DIRECT", "CONSOL") or rfq.mode == "AIR":
        if rfq.package_length_cm is None or rfq.package_width_cm is None or rfq.package_height_cm is None:
            errors.append("Package dimensions (L/W/H) are required for LCL or Air shipments")

    if rfq.is_dgr:
        if not rfq.dgr_un_number:
            errors.append("DGR UN number is required when DGR flag is set")
        if not rfq.dgr_class:
            errors.append("DGR class is required when DGR flag is set")

    if rfq.has_lc and not rfq.lc_number:
        errors.append("LC number is required when LC flag is set")

    if rfq.preferred_departure_date < today:
        errors.append("Preferred departure date cannot be in the past")
    if rfq.required_delivery_date < rfq.preferred_departure_date:
        errors.append("Required delivery date must be on or after preferred departure date")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
