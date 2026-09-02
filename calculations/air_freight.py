"""
Air Freight Chargeable Weight Calculator.

- Volumetric weight per piece = (L x W x H) / divisor  (default divisor: 6000)
- Total volumetric weight = sum across all pieces
- Chargeable weight = MAX(total_gross_weight, total_volumetric_weight)
- Pivot / Break Weight Optimization: evaluates rate breaks (+45, +100, +250, +500, +1000)
  to identify if paying for a higher break weight reduces total freight charge.
"""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_VOLUMETRIC_DIVISOR = 6000


@dataclass
class Package:
    gross_weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    quantity: int = 1


@dataclass
class ChargeableWeightResult:
    total_gross_weight_kg: float
    total_volumetric_weight_kg: float
    chargeable_weight_kg: float
    basis: str  # "GROSS" or "VOLUMETRIC"


@dataclass
class RateBreak:
    weight_break_kg: float  # e.g. 0 (min/normal), 45, 100, 250, 500, 1000
    rate_per_kg: float


@dataclass
class PivotOptimizationResult:
    actual_chargeable_weight_kg: float
    actual_rate_per_kg: float
    actual_total_cost: float
    optimized_weight_kg: float
    optimized_rate_per_kg: float
    optimized_total_cost: float
    savings_amount: float
    savings_pct: float
    recommendation: str
    is_optimized: bool = False


def calculate_volumetric_weight(package: Package, divisor: int = DEFAULT_VOLUMETRIC_DIVISOR) -> float:
    per_piece = (package.length_cm * package.width_cm * package.height_cm) / divisor
    return per_piece * package.quantity


def calculate_chargeable_weight(packages: list[Package], divisor: int = DEFAULT_VOLUMETRIC_DIVISOR) -> ChargeableWeightResult:
    if not packages:
        raise ValueError("At least one package is required")

    total_gross = sum(p.gross_weight_kg * p.quantity for p in packages)
    total_volumetric = sum(calculate_volumetric_weight(p, divisor) for p in packages)

    chargeable = max(total_gross, total_volumetric)
    basis = "VOLUMETRIC" if total_volumetric > total_gross else "GROSS"

    return ChargeableWeightResult(
        total_gross_weight_kg=round(total_gross, 2),
        total_volumetric_weight_kg=round(total_volumetric, 2),
        chargeable_weight_kg=round(chargeable, 2),
        basis=basis,
    )


def calculate_pivot_weight_optimization(
    actual_chargeable_weight: float,
    rate_breaks: list[RateBreak],
) -> PivotOptimizationResult:
    """
    Evaluates rate breaks higher than actual chargeable weight to determine
    if 'bumping' to a higher break weight yields a lower total freight charge.
    """
    if not rate_breaks:
        raise ValueError("Rate breaks are required for optimization")

    # Sort rate breaks by break weight ascending
    sorted_breaks = sorted(rate_breaks, key=lambda b: b.weight_break_kg)

    # Determine applicable rate at actual weight
    applicable_break = sorted_breaks[0]
    for b in sorted_breaks:
        if actual_chargeable_weight >= b.weight_break_kg:
            applicable_break = b

    actual_rate = applicable_break.rate_per_kg
    actual_total = round(actual_chargeable_weight * actual_rate, 2)

    best_weight = actual_chargeable_weight
    best_rate = actual_rate
    best_total = actual_total
    is_optimized = False

    # Check each break weight above actual chargeable weight
    for b in sorted_breaks:
        if b.weight_break_kg > actual_chargeable_weight:
            break_total = round(b.weight_break_kg * b.rate_per_kg, 2)
            if break_total < best_total:
                best_weight = b.weight_break_kg
                best_rate = b.rate_per_kg
                best_total = break_total
                is_optimized = True

    savings = round(actual_total - best_total, 2)
    savings_pct = round((savings / actual_total) * 100, 2) if actual_total > 0 else 0.0

    if is_optimized:
        recommendation = (
            f"Bump to {best_weight} kg break at ${best_rate}/kg: saves ${savings} ({savings_pct}%) "
            f"vs actual {actual_chargeable_weight} kg at ${actual_rate}/kg"
        )
    else:
        recommendation = f"Rate as actual {actual_chargeable_weight} kg at ${actual_rate}/kg (optimal)"

    return PivotOptimizationResult(
        actual_chargeable_weight_kg=actual_chargeable_weight,
        actual_rate_per_kg=actual_rate,
        actual_total_cost=actual_total,
        optimized_weight_kg=best_weight,
        optimized_rate_per_kg=best_rate,
        optimized_total_cost=best_total,
        savings_amount=savings,
        savings_pct=savings_pct,
        recommendation=recommendation,
        is_optimized=is_optimized,
    )
