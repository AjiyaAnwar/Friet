"""
Sea Freight LCL Revenue Ton Calculator.

- Revenue Tons (W/M) = MAX(Gross Weight kg / 1000, CBM)
- Minimum charge enforcement: if W/M falls below carrier minimum, apply minimum
"""

from dataclasses import dataclass


@dataclass
class RevenueTonResult:
    weight_tons: float
    volume_cbm: float
    revenue_tons: float
    basis: str  # "WEIGHT" or "VOLUME"
    minimum_applied: bool
    billable_revenue_tons: float


def calculate_lcl_revenue_tons(
    gross_weight_kg: float,
    total_cbm: float,
    carrier_minimum_rt: float = 1.0,
) -> RevenueTonResult:
    if gross_weight_kg < 0 or total_cbm < 0:
        raise ValueError("Weight and volume must be non-negative")

    weight_tons = gross_weight_kg / 1000
    revenue_tons = max(weight_tons, total_cbm)
    basis = "VOLUME" if total_cbm > weight_tons else "WEIGHT"

    minimum_applied = revenue_tons < carrier_minimum_rt
    billable = carrier_minimum_rt if minimum_applied else revenue_tons

    return RevenueTonResult(
        weight_tons=round(weight_tons, 3),
        volume_cbm=round(total_cbm, 3),
        revenue_tons=round(revenue_tons, 3),
        basis=basis,
        minimum_applied=minimum_applied,
        billable_revenue_tons=round(billable, 3),
    )