import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.modules.commercial.calculations.container_utilization import calculate_container_utilization


def test_normal_utilization_no_warnings():
    result = calculate_container_utilization(
        total_cbm=20, gross_weight_kg=10000, container_type="20GP"
    )
    assert result.volume_utilization_pct < 95
    assert result.weight_utilization_pct < 90
    assert result.warnings == []
    assert result.suggested_container_type is None


def test_high_volume_triggers_warning_and_suggestion():
    result = calculate_container_utilization(
        total_cbm=66, gross_weight_kg=5000, container_type="40GP"
    )
    assert result.volume_utilization_pct > 95
    assert len(result.warnings) == 1
    assert result.suggested_container_type == "40HC"


def test_high_weight_triggers_warning():
    result = calculate_container_utilization(
        total_cbm=10, gross_weight_kg=27000, container_type="20GP"
    )
    assert result.weight_utilization_pct > 90
    assert any("Weight utilization" in w for w in result.warnings)
    assert result.suggested_container_type == "40GP"


def test_effective_utilization_is_the_minimum():
    result = calculate_container_utilization(
        total_cbm=30, gross_weight_kg=5000, container_type="20GP"
    )
    assert result.effective_utilization_pct == min(
        result.volume_utilization_pct, result.weight_utilization_pct
    )


def test_unknown_container_type_raises_error():
    with pytest.raises(ValueError):
        calculate_container_utilization(
            total_cbm=10, gross_weight_kg=5000, container_type="BOGUS"
        )