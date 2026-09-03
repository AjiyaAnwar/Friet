import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date
from app.modules.commercial.calculations.rate_selection import Rate, RateCategory, select_rate, compare_carrier_rates

TODAY = date(2026, 9, 2)
VALID_FROM = date(2026, 1, 1)
VALID_TO = date(2026, 12, 31)


def make_rate(**overrides):
    defaults = dict(
        rate_id="R1", category=RateCategory.FAK, carrier="Maersk",
        origin="PKKAR", destination="AEJEA", base_amount=500.0,
        currency="USD", effective_date=VALID_FROM, expiry_date=VALID_TO,
        status="ACTIVE", customer_id=None,
    )
    defaults.update(overrides)
    return Rate(**defaults)


def test_customer_contract_rate_wins_over_everything():
    rates = [
        make_rate(rate_id="FAK1", category=RateCategory.FAK, base_amount=400),
        make_rate(rate_id="NAC1", category=RateCategory.CONTRACT_NAC, base_amount=600, customer_id="CUST-1"),
    ]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.selected_rate.rate_id == "NAC1"
    assert result.no_rate_available is False


def test_contract_rate_for_different_customer_is_ignored():
    rates = [
        make_rate(rate_id="NAC1", category=RateCategory.CONTRACT_NAC, base_amount=600, customer_id="CUST-OTHER"),
        make_rate(rate_id="FAK1", category=RateCategory.FAK, base_amount=400),
    ]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.selected_rate.rate_id == "FAK1"


def test_falls_through_cascade_to_fak_when_nothing_else_exists():
    rates = [make_rate(rate_id="FAK1", category=RateCategory.FAK, base_amount=400)]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.selected_rate.rate_id == "FAK1"


def test_expired_rate_is_skipped():
    rates = [
        make_rate(rate_id="EXPIRED_NAC", category=RateCategory.CONTRACT_NAC,
                   customer_id="CUST-1", base_amount=100, expiry_date=date(2026, 1, 1)),
        make_rate(rate_id="FAK1", category=RateCategory.FAK, base_amount=400),
    ]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.selected_rate.rate_id == "FAK1"


def test_wrong_lane_is_ignored():
    rates = [make_rate(rate_id="WRONG_LANE", origin="PKKAR", destination="USNYC", base_amount=100)]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.no_rate_available is True


def test_no_rate_available_when_nothing_matches():
    result = select_rate("CUST-1", "PKKAR", "AEJEA", [], today=TODAY)
    assert result.no_rate_available is True
    assert result.selected_rate is None


def test_cheapest_wins_within_same_category():
    rates = [
        make_rate(rate_id="FAK_EXPENSIVE", category=RateCategory.FAK, base_amount=900),
        make_rate(rate_id="FAK_CHEAP", category=RateCategory.FAK, base_amount=300),
    ]
    result = select_rate("CUST-1", "PKKAR", "AEJEA", rates, today=TODAY)
    assert result.selected_rate.rate_id == "FAK_CHEAP"


def test_compare_carrier_rates_returns_all_sorted_cheapest_first():
    rates = [
        make_rate(rate_id="R1", carrier="Maersk", base_amount=500),
        make_rate(rate_id="R2", carrier="CMA CGM", base_amount=300),
        make_rate(rate_id="R3", carrier="MSC", base_amount=700),
    ]
    results = compare_carrier_rates("PKKAR", "AEJEA", rates, today=TODAY)
    assert [r.rate_id for r in results] == ["R2", "R1", "R3"]