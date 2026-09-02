import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from calculations.quotation_engine import (
    ChargeLine, ChargeCategory, build_quotation_option,
    MarginRule, evaluate_margin_rules,
)


def sample_charge_lines():
    return [
        ChargeLine("Ocean Freight", ChargeCategory.FREIGHT, cost_amount=800, sell_amount=950),
        ChargeLine("BAF", ChargeCategory.SURCHARGE, cost_amount=50, sell_amount=60),
        ChargeLine("THC Destination", ChargeCategory.LOCAL, cost_amount=100, sell_amount=130),
    ]


def test_totals_are_calculated_correctly():
    option = build_quotation_option("Option A - Cheapest", sample_charge_lines())
    assert option.total_cost == 950
    assert option.total_sell == 1140
    assert option.gross_margin == 190
    assert option.margin_pct == pytest.approx(16.67, rel=0.01)


def test_empty_charge_lines_raises_error():
    with pytest.raises(ValueError):
        build_quotation_option("Empty", [])


def test_margin_passes_when_above_minimum():
    option = build_quotation_option("Option A", sample_charge_lines())
    rules = [MarginRule(service_type="SEA_FCL", min_margin_pct=5.0)]
    result = evaluate_margin_rules(option, "SEA_FCL", rules)
    assert result.passes is True
    assert result.violations == []


def test_margin_fails_when_below_minimum():
    thin_margin_lines = [
        ChargeLine("Ocean Freight", ChargeCategory.FREIGHT, cost_amount=1000, sell_amount=1010),
    ]
    option = build_quotation_option("Thin", thin_margin_lines)
    rules = [MarginRule(service_type="SEA_FCL", min_margin_pct=5.0)]
    result = evaluate_margin_rules(option, "SEA_FCL", rules)
    assert result.passes is False
    assert len(result.violations) == 1


def test_min_margin_amount_rule():
    option = build_quotation_option("Small shipment", [
        ChargeLine("Freight", ChargeCategory.FREIGHT, cost_amount=100, sell_amount=110),
    ])
    rules = [MarginRule(service_type="AIR", min_margin_amount=50.0)]
    result = evaluate_margin_rules(option, "AIR", rules)
    assert result.passes is False
    assert any("Margin amount" in v for v in result.violations)


def test_customer_tier_override_lowers_threshold():
    option = build_quotation_option("Option A", [
        ChargeLine("Freight", ChargeCategory.FREIGHT, cost_amount=1000, sell_amount=1040),
    ])
    rules = [MarginRule(
        service_type="SEA_FCL", min_margin_pct=5.0,
        customer_tier_override_pct={"A": 3.0},
    )]

    result_regular = evaluate_margin_rules(option, "SEA_FCL", rules, customer_tier=None)
    assert result_regular.passes is False

    result_a_tier = evaluate_margin_rules(option, "SEA_FCL", rules, customer_tier="A")
    assert result_a_tier.passes is True


def test_wildcard_rule_applies_to_all_service_types():
    option = build_quotation_option("Option A", [
        ChargeLine("Freight", ChargeCategory.FREIGHT, cost_amount=1000, sell_amount=1010),
    ])
    rules = [MarginRule(service_type="*", min_margin_pct=5.0)]
    result = evaluate_margin_rules(option, "AIR", rules)
    assert result.passes is False


def test_no_applicable_rules_always_passes():
    option = build_quotation_option("Option A", sample_charge_lines())
    rules = [MarginRule(service_type="AIR", min_margin_pct=50.0)]
    result = evaluate_margin_rules(option, "SEA_LCL", rules)
    assert result.passes is True


def test_lane_override_takes_precedence():
    option = build_quotation_option("Option A", [
        ChargeLine("Freight", ChargeCategory.FREIGHT, cost_amount=1000, sell_amount=1030),  # 2.91% margin
    ])
    rules = [MarginRule(
        service_type="SEA_FCL",
        min_margin_pct=5.0,
        customer_tier_overrides={"A": 4.0},
        lane_overrides={"PKKAR-AEJEA": 2.5},
    )]
    # Default without lane -> fails
    res1 = evaluate_margin_rules(option, "SEA_FCL", rules, customer_tier="A")
    assert res1.passes is False

    # With lane code -> passes (threshold lowered to 2.5%)
    res2 = evaluate_margin_rules(option, "SEA_FCL", rules, customer_tier="A", lane_code="PKKAR-AEJEA")
    assert res2.passes is True
    assert res2.effective_min_margin_pct == 2.5