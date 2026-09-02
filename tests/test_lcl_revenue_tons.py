import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from calculations.lcl_revenue_tons import calculate_lcl_revenue_tons


def test_weight_basis_wins_for_dense_cargo():
    result = calculate_lcl_revenue_tons(gross_weight_kg=1500, total_cbm=1.0)
    assert result.weight_tons == 1.5
    assert result.revenue_tons == 1.5
    assert result.basis == "WEIGHT"


def test_volume_basis_wins_for_bulky_cargo():
    result = calculate_lcl_revenue_tons(gross_weight_kg=200, total_cbm=3.0)
    assert result.revenue_tons == 3.0
    assert result.basis == "VOLUME"


def test_minimum_charge_applied_when_shipment_is_tiny():
    result = calculate_lcl_revenue_tons(
        gross_weight_kg=100, total_cbm=0.3, carrier_minimum_rt=1.0
    )
    assert result.revenue_tons == 0.3
    assert result.minimum_applied is True
    assert result.billable_revenue_tons == 1.0


def test_no_minimum_applied_when_shipment_exceeds_it():
    result = calculate_lcl_revenue_tons(
        gross_weight_kg=2000, total_cbm=2.5, carrier_minimum_rt=1.0
    )
    assert result.minimum_applied is False
    assert result.billable_revenue_tons == result.revenue_tons


def test_negative_inputs_raise_error():
    with pytest.raises(ValueError):
        calculate_lcl_revenue_tons(gross_weight_kg=-5, total_cbm=1.0)