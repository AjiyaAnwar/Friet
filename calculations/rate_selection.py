"""
Automatic Rate Selection Engine.

Priority cascade for selecting which rate to use on a given RFQ:
    1. Customer-specific contract rate (NAC)
    2. Customer-specific spot rate
    3. NAC rate for the trade lane (not customer-specific)
    4. Promotional rate
    5. Best FAK rate
    6. Agent rate (fallback, mainly for local charges)
    7. NO_RATE_AVAILABLE -> flag for manual pricing

Supports both the legacy flat Rate structure and the full 4-tier
Rate -> RateVersion -> RateLine + RateSurcharge domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RateCategory(str, Enum):
    CONTRACT_NAC = "CONTRACT_NAC"
    SPOT = "SPOT"
    LANE_NAC = "LANE_NAC"
    PROMOTIONAL = "PROMOTIONAL"
    FAK = "FAK"
    AGENT = "AGENT"


CATEGORY_PRIORITY = [
    RateCategory.CONTRACT_NAC,
    RateCategory.SPOT,
    RateCategory.LANE_NAC,
    RateCategory.PROMOTIONAL,
    RateCategory.FAK,
    RateCategory.AGENT,
]


@dataclass
class Rate:
    rate_id: str
    category: RateCategory
    carrier: str
    origin: str
    destination: str
    base_amount: float
    currency: str
    effective_date: date
    expiry_date: date
    status: str
    customer_id: str | None = None
    commodity_id: str | None = None
    versions: list[Any] = field(default_factory=list)


@dataclass
class RateSelectionResult:
    selected_rate: Any | None
    reason: str
    no_rate_available: bool = False
    applicable_version: Any | None = None
    resolved_lines: list[Any] = field(default_factory=list)
    attached_surcharges: list[Any] = field(default_factory=list)
    total_freight_cost: float = 0.0


def _is_valid(rate: Any, today: date) -> bool:
    status = rate.status.value if hasattr(rate.status, "value") else str(rate.status)
    return status == "ACTIVE" and rate.effective_date <= today <= rate.expiry_date


def select_rate(
    customer_id: str,
    origin: str,
    destination: str,
    available_rates: list[Any],
    today: date | None = None,
    weight_kg: float | None = None,
    container_type: str | None = None,
) -> RateSelectionResult:
    if today is None:
        today = date.today()

    lane_rates = []
    for r in available_rates:
        r_origin = getattr(r, "origin_location_id", getattr(r, "origin", None))
        r_dest = getattr(r, "destination_location_id", getattr(r, "destination", None))
        if r_origin == origin and r_dest == destination and _is_valid(r, today):
            lane_rates.append(r)

    for category in CATEGORY_PRIORITY:
        candidates = []
        for r in lane_rates:
            cat = getattr(r, "rate_category", getattr(r, "category", None))
            cat_val = cat.value if hasattr(cat, "value") else str(cat)
            if cat_val == category.value:
                candidates.append(r)

        if category in (RateCategory.CONTRACT_NAC, RateCategory.SPOT):
            candidates = [r for r in candidates if getattr(r, "customer_id", None) == customer_id]

        if not candidates:
            continue

        # Check if candidate has versions / lines
        first = candidates[0]
        if hasattr(first, "versions") and first.versions:
            # Domain Rate entity with 4-tier structure
            best_rate = candidates[0]
            best_version = best_rate.current_version
            rate_id_val = getattr(best_rate, "rate_number", getattr(best_rate, "rate_id", best_rate.id))

            resolved_lines = []
            if best_version:
                for line in best_version.lines:
                    if weight_kg is not None and line.weight_break_from is not None:
                        wb_to = line.weight_break_to or float("inf")
                        if line.weight_break_from <= weight_kg < wb_to:
                            resolved_lines.append(line)
                    elif container_type and line.container_type_code:
                        if line.container_type_code == container_type:
                            resolved_lines.append(line)
                    else:
                        resolved_lines.append(line)

            return RateSelectionResult(
                selected_rate=best_rate,
                reason=f"Selected {category.value} rate {rate_id_val}",
                applicable_version=best_version,
                resolved_lines=resolved_lines,
                attached_surcharges=best_version.surcharges if best_version else [],
            )

        # Legacy flat rate
        best = min(candidates, key=lambda r: getattr(r, "base_amount", 0.0))
        rate_id_val = getattr(best, "rate_number", getattr(best, "rate_id", None))
        return RateSelectionResult(
            selected_rate=best,
            reason=f"Selected {category.value} rate {rate_id_val}",
            total_freight_cost=getattr(best, "base_amount", 0.0),
        )

    return RateSelectionResult(
        selected_rate=None,
        reason="No valid rate found in any category for this lane",
        no_rate_available=True,
    )


def compare_carrier_rates(
    origin: str,
    destination: str,
    available_rates: list[Any],
    today: date | None = None,
) -> list[Any]:
    if today is None:
        today = date.today()

    valid = []
    for r in available_rates:
        r_origin = getattr(r, "origin_location_id", getattr(r, "origin", None))
        r_dest = getattr(r, "destination_location_id", getattr(r, "destination", None))
        if r_origin == origin and r_dest == destination and _is_valid(r, today):
            valid.append(r)

    return sorted(valid, key=lambda r: getattr(r, "base_amount", 0.0))
