"""
Rate Resolution: given a rate version's lines, resolve the actual amount
to charge for a specific shipment.
"""

from datetime import date

from rate_engine.models import RateLine, RateSurcharge


class RateResolutionError(Exception):
    pass


def resolve_weight_break_rate(lines: list[RateLine], chargeable_weight_kg: float) -> RateLine:
    weight_lines = [l for l in lines if l.weight_break_from is not None]
    if not weight_lines:
        raise RateResolutionError("No weight-break rate lines found on this rate version")

    candidates = [
        l for l in weight_lines
        if l.weight_break_from <= chargeable_weight_kg
        and (l.weight_break_to is None or chargeable_weight_kg <= l.weight_break_to)
    ]

    if not candidates:
        raise RateResolutionError(
            f"No weight break covers chargeable weight {chargeable_weight_kg}kg"
        )

    return max(candidates, key=lambda l: l.weight_break_from)


def resolve_pivot_weight_option(lines: list[RateLine], actual_weight_kg: float) -> dict:
    actual_line = resolve_weight_break_rate(lines, actual_weight_kg)
    actual_total = actual_line.amount * actual_weight_kg

    weight_lines = sorted(
        [l for l in lines if l.weight_break_from is not None],
        key=lambda l: l.weight_break_from,
    )

    cheaper_option = None
    for line in weight_lines:
        if line.weight_break_from > actual_weight_kg:
            pivot_total = line.amount * line.weight_break_from
            if pivot_total < actual_total:
                cheaper_option = {
                    "break_weight_kg": line.weight_break_from,
                    "rate_per_kg": line.amount,
                    "total_charge": round(pivot_total, 2),
                }
            break

    return {
        "actual_weight_kg": actual_weight_kg,
        "actual_rate_per_kg": actual_line.amount,
        "actual_total_charge": round(actual_total, 2),
        "cheaper_pivot_option": cheaper_option,
        "recommendation": "USE_PIVOT" if cheaper_option else "USE_ACTUAL",
    }


def resolve_container_rate(lines: list[RateLine], container_type_code: str) -> RateLine:
    matches = [l for l in lines if l.container_type_code == container_type_code]
    if not matches:
        raise RateResolutionError(
            f"No rate line found for container type '{container_type_code}'"
        )
    if len(matches) > 1:
        return min(matches, key=lambda l: l.amount)
    return matches[0]


def resolve_applicable_surcharges(
    surcharges: list[RateSurcharge], on_date: date
) -> list[RateSurcharge]:
    return [
        s for s in surcharges
        if s.applicable_from <= on_date <= s.applicable_to
    ]