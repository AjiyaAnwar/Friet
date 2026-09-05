import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from datetime import date
from app.modules.commercial.rate_engine.models import RateLine, RateSurcharge
from app.modules.commercial.rate_engine.resolution import (
    resolve_weight_break_rate, resolve_pivot_weight_option,
    resolve_container_rate, resolve_applicable_surcharges,
    RateResolutionError,
)


def air_weight_break_lines():
    breaks = [
        (0, 45, 8.0),
        (45, 100, 6.5),
        (100, 250, 5.0),
        (250, 500, 4.2),
        (500, 1000, 3.5),
        (1000, None, 2.8),
    ]
    return [
        RateLine(id=f"L{i}", rate_version_id="V1", charge_code="AFR", rate_basis="PER_KG",
                  weight_break_from=frm, weight_break_to=to, container_type_code=None, amount=amt)
        for i, (frm, to, amt) in enumerate(breaks)
    ]


def test_resolves_correct_weight_break():
    lines = air_weight_break_lines()
    result = resolve_weight_break_rate(lines, 60)
    assert result.amount == 6.5


def test_resolves_lowest_break():
    lines = air_weight_break_lines()
    result = resolve_weight_break_rate(lines, 10)
    assert result.amount == 8.0


def test_resolves_open_ended_top_break():
    lines = air_weight_break_lines()
    result = resolve_weight_break_rate(lines, 5000)
    assert result.amount == 2.8


def test_resolves_boundary_weight_exactly():
    lines = air_weight_break_lines()
    result = resolve_weight_break_rate(lines, 100)
    assert result.amount == 5.0


def test_no_weight_lines_raises():
    with pytest.raises(RateResolutionError):
        resolve_weight_break_rate([], 60)


def test_pivot_weight_finds_cheaper_option():
    lines = air_weight_break_lines()
    result = resolve_pivot_weight_option(lines, 95)
    assert result["actual_total_charge"] == 617.5
    assert result["cheaper_pivot_option"] is not None
    assert result["cheaper_pivot_option"]["total_charge"] == 500.0
    assert result["recommendation"] == "USE_PIVOT"


def test_pivot_weight_no_cheaper_option_when_not_worth_it():
    lines = air_weight_break_lines()
    result = resolve_pivot_weight_option(lines, 10)
    assert result["cheaper_pivot_option"] is None
    assert result["recommendation"] == "USE_ACTUAL"


def test_container_rate_resolution():
    lines = [
        RateLine(id="L1", rate_version_id="V1", charge_code="OFR", rate_basis="FLAT",
                  weight_break_from=None, weight_break_to=None, container_type_code="20GP", amount=800),
        RateLine(id="L2", rate_version_id="V1", charge_code="OFR", rate_basis="FLAT",
                  weight_break_from=None, weight_break_to=None, container_type_code="40GP", amount=1200),
    ]
    result = resolve_container_rate(lines, "40GP")
    assert result.amount == 1200


def test_container_rate_not_found_raises():
    lines = [
        RateLine(id="L1", rate_version_id="V1", charge_code="OFR", rate_basis="FLAT",
                  weight_break_from=None, weight_break_to=None, container_type_code="20GP", amount=800),
    ]
    with pytest.raises(RateResolutionError):
        resolve_container_rate(lines, "40HC")


def test_surcharge_resolution_filters_by_date():
    surcharges = [
        RateSurcharge(id="S1", rate_version_id="V1", charge_code="BAF", basis="PER_KG",
                       amount=0.5, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 6, 30)),
        RateSurcharge(id="S2", rate_version_id="V1", charge_code="PSS", basis="FLAT",
                       amount=50, applicable_from=date(2026, 7, 1), applicable_to=date(2026, 12, 31)),
    ]
    result = resolve_applicable_surcharges(surcharges, date(2026, 3, 15))
    assert len(result) == 1
    assert result[0].charge_code == "BAF"


def test_surcharge_resolution_returns_none_when_none_apply():
    surcharges = [
        RateSurcharge(id="S1", rate_version_id="V1", charge_code="BAF", basis="PER_KG",
                       amount=0.5, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 6, 30)),
    ]
    result = resolve_applicable_surcharges(surcharges, date(2027, 1, 1))
    assert result == []