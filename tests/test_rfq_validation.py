import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date
from calculations.rfq_validation import RfqInput, validate_rfq

TODAY = date(2026, 9, 2)


def base_rfq(**overrides):
    defaults = dict(
        service_type="FCL",
        mode="SEA",
        cargo_readiness_date=date(2026, 9, 5),
        preferred_departure_date=date(2026, 9, 10),
        required_delivery_date=date(2026, 9, 20),
        container_types=["40GP"],
    )
    defaults.update(overrides)
    return RfqInput(**defaults)


def test_valid_fcl_rfq_passes():
    rfq = base_rfq()
    result = validate_rfq(rfq, today=TODAY)
    assert result.is_valid is True
    assert result.errors == []


def test_fcl_without_container_type_fails():
    rfq = base_rfq(container_types=[])
    result = validate_rfq(rfq, today=TODAY)
    assert result.is_valid is False
    assert any("Container type" in e for e in result.errors)


def test_lcl_without_dimensions_fails():
    rfq = base_rfq(service_type="LCL", container_types=[])
    result = validate_rfq(rfq, today=TODAY)
    assert any("dimensions" in e for e in result.errors)


def test_lcl_with_dimensions_passes():
    rfq = base_rfq(
        service_type="LCL",
        container_types=[],
        package_length_cm=50,
        package_width_cm=40,
        package_height_cm=30,
    )
    result = validate_rfq(rfq, today=TODAY)
    assert result.is_valid is True


def test_dgr_without_subform_fails():
    rfq = base_rfq(is_dgr=True)
    result = validate_rfq(rfq, today=TODAY)
    assert any("DGR UN number" in e for e in result.errors)
    assert any("DGR class" in e for e in result.errors)


def test_dgr_with_subform_passes():
    rfq = base_rfq(is_dgr=True, dgr_un_number="UN1234", dgr_class="3")
    result = validate_rfq(rfq, today=TODAY)
    assert result.is_valid is True


def test_lc_flag_without_number_fails():
    rfq = base_rfq(has_lc=True)
    result = validate_rfq(rfq, today=TODAY)
    assert any("LC number" in e for e in result.errors)


def test_departure_date_in_past_fails():
    rfq = base_rfq(preferred_departure_date=date(2026, 8, 1))
    result = validate_rfq(rfq, today=TODAY)
    assert any("past" in e for e in result.errors)


def test_delivery_before_departure_fails():
    rfq = base_rfq(
        preferred_departure_date=date(2026, 9, 10),
        required_delivery_date=date(2026, 9, 5),
    )
    result = validate_rfq(rfq, today=TODAY)
    assert any("on or after" in e for e in result.errors)


def test_multiple_errors_all_reported():
    rfq = base_rfq(container_types=[], is_dgr=True, has_lc=True)
    result = validate_rfq(rfq, today=TODAY)
    assert len(result.errors) >= 4