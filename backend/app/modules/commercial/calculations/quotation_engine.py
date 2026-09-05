"""
Quotation Engine.

- Each quotation option is built from charge lines (freight, surcharges,
  local charges, agent fees).
- Totals: subtotal cost, subtotal sell, gross margin, margin %.
- Margin Rules Engine: evaluate against configured minimum margin rules;
  supports service type, min margin amount, customer tier overrides, and lane overrides.
  If any rule fails, the quotation option is flagged is_below_margin=True and needs
  Pricing Manager approval before it can be sent to the customer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChargeCategory(str, Enum):
    FREIGHT = "FREIGHT"
    SURCHARGE = "SURCHARGE"
    LOCAL = "LOCAL"
    AGENT = "AGENT"


@dataclass
class ChargeLine:
    description: str
    category: ChargeCategory
    cost_amount: float
    sell_amount: float
    charge_code: str = "GENERIC"
    rate_version_id: str | None = None


@dataclass
class QuotationOption:
    label: str
    charge_lines: list[Any]
    route_id: str | None = None
    primary_rate_version_id: str | None = None
    currency_code: str = "USD"
    is_below_margin: bool = False

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


def build_quotation_option(label: str, charge_lines: list[Any], currency_code: str = "USD") -> QuotationOption:
    if not charge_lines:
        raise ValueError("A quotation option needs at least one charge line")
    return QuotationOption(label=label, charge_lines=charge_lines, currency_code=currency_code)


@dataclass
class MarginRule:
    service_type: str
    min_margin_pct: float | None = None
    min_margin_amount: float | None = None
    customer_tier_override_pct: dict[str, float] = field(default_factory=dict)
    customer_tier_overrides: dict[str, float] = field(default_factory=dict)
    lane_overrides: dict[str, float] = field(default_factory=dict)  # {"PKKAR-AEJEA": 4.0}


@dataclass
class MarginEvaluationResult:
    passes: bool
    violations: list[str] = field(default_factory=list)
    effective_min_margin_pct: float | None = None


def evaluate_margin_rules(
    option: QuotationOption,
    service_type: str,
    rules: list[MarginRule],
    customer_tier: str | None = None,
    lane_code: str | None = None,
) -> MarginEvaluationResult:
    applicable = [r for r in rules if r.service_type in (service_type, "*")]

    violations: list[str] = []
    effective_min_pct = None

    for rule in applicable:
        min_pct = rule.min_margin_pct

        # Check lane override first (most specific)
        if lane_code and rule.lane_overrides and lane_code in rule.lane_overrides:
            min_pct = rule.lane_overrides[lane_code]
        # Then check customer tier override
        elif customer_tier:
            overrides = rule.customer_tier_overrides or rule.customer_tier_override_pct
            if customer_tier in overrides:
                min_pct = overrides[customer_tier]

        if min_pct is not None:
            effective_min_pct = min_pct
            if option.margin_pct < min_pct:
                violations.append(
                    f"Margin {option.margin_pct}% is below minimum {min_pct}% "
                    f"required for {service_type}"
                )

        if rule.min_margin_amount is not None and option.gross_margin < rule.min_margin_amount:
            violations.append(
                f"Margin amount {option.gross_margin} is below minimum "
                f"{rule.min_margin_amount} required for {service_type}"
            )

    passes = len(violations) == 0
    option.is_below_margin = not passes

    return MarginEvaluationResult(
        passes=passes,
        violations=violations,
        effective_min_margin_pct=effective_min_pct,
    )
