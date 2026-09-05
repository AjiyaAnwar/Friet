import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.modules.commercial.calculations.air_freight import Package, calculate_chargeable_weight


def test_gross_weight_wins_when_dense_cargo():
    packages = [Package(gross_weight_kg=50, length_cm=30, width_cm=30, height_cm=30)]
    result = calculate_chargeable_weight(packages)
    assert result.total_gross_weight_kg == 50
    assert result.chargeable_weight_kg == 50
    assert result.basis == "GROSS"


def test_volumetric_weight_wins_when_bulky_light_cargo():
    packages = [Package(gross_weight_kg=5, length_cm=100, width_cm=100, height_cm=100)]
    result = calculate_chargeable_weight(packages)
    assert result.total_volumetric_weight_kg == 166.67
    assert result.chargeable_weight_kg == 166.67
    assert result.basis == "VOLUMETRIC"


def test_multiple_packages_are_summed():
    packages = [
        Package(gross_weight_kg=10, length_cm=40, width_cm=40, height_cm=40, quantity=2),
        Package(gross_weight_kg=5, length_cm=20, width_cm=20, height_cm=20, quantity=1),
    ]
    result = calculate_chargeable_weight(packages)
    assert result.total_gross_weight_kg == 25
    assert result.chargeable_weight_kg >= result.total_gross_weight_kg


def test_custom_divisor_for_specific_carrier():
    packages = [Package(gross_weight_kg=5, length_cm=100, width_cm=100, height_cm=100)]
    result = calculate_chargeable_weight(packages, divisor=5000)
    assert result.total_volumetric_weight_kg == 200


def test_empty_package_list_raises_error():
    with pytest.raises(ValueError):
        calculate_chargeable_weight([])


def test_pivot_weight_optimization_no_saving():
    from app.modules.commercial.calculations.air_freight import RateBreak, calculate_pivot_weight_optimization
    rate_breaks = [
        RateBreak(weight_break_kg=0, rate_per_kg=5.0),
        RateBreak(weight_break_kg=45, rate_per_kg=4.0),
    ]
    # At 40 kg: 40 * 5 = 200. At 45 kg: 45 * 4 = 180.
    res1 = calculate_pivot_weight_optimization(40.0, rate_breaks)
    assert res1.is_optimized is True
    assert res1.optimized_weight_kg == 45.0
    assert res1.optimized_total_cost == 180.0
    assert res1.savings_amount == 20.0

    # At 20 kg: 20 * 5 = 100. At 45 kg: 45 * 4 = 180. No optimization.
    res2 = calculate_pivot_weight_optimization(20.0, rate_breaks)
    assert res2.is_optimized is False
    assert res2.optimized_weight_kg == 20.0
    assert res2.optimized_total_cost == 100.0
    assert res2.savings_amount == 0.0