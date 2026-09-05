import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date
from app.modules.commercial.rate_engine.models import Rate
from app.modules.commercial.rate_engine.expiry import check_rate_expiry, apply_auto_expiry

TODAY = date(2026, 9, 2)


def make_rate(**overrides):
    defaults = dict(
        id="R1", rate_number="RT-001", rate_type="AIR_FREIGHT", rate_category="FAK",
        carrier_vendor_id="C1", service_name="Standard", origin_location_id="L1",
        destination_location_id="L2", via_routing=None, commodity_id=None, customer_id=None,
        effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31),
        currency_code="USD", status="ACTIVE",
    )
    defaults.update(overrides)
    return Rate(**defaults)


def test_rate_expiring_in_5_days_is_warning():
    rate = make_rate(expiry_date=date(2026, 9, 7))
    result = check_rate_expiry([rate], TODAY)
    assert rate in result.warning
    assert rate not in result.escalation


def test_rate_expiring_in_2_days_is_escalation():
    rate = make_rate(expiry_date=date(2026, 9, 4))
    result = check_rate_expiry([rate], TODAY)
    assert rate in result.escalation
    assert rate not in result.warning


def test_rate_already_expired_is_newly_expired():
    rate = make_rate(expiry_date=date(2026, 8, 1), status="ACTIVE")
    result = check_rate_expiry([rate], TODAY)
    assert rate in result.newly_expired


def test_rate_far_from_expiry_is_ignored():
    rate = make_rate(expiry_date=date(2027, 1, 1))
    result = check_rate_expiry([rate], TODAY)
    assert result.warning == []
    assert result.escalation == []
    assert result.newly_expired == []


def test_already_expired_rate_not_flagged_again():
    rate = make_rate(expiry_date=date(2026, 8, 1), status="EXPIRED")
    result = check_rate_expiry([rate], TODAY)
    assert rate not in result.newly_expired


def test_apply_auto_expiry_transitions_status():
    rate = make_rate(expiry_date=date(2026, 8, 1), status="ACTIVE")
    updated = apply_auto_expiry([rate], TODAY)
    assert updated[0].status == "EXPIRED"


def test_apply_auto_expiry_leaves_valid_rates_untouched():
    rate = make_rate(expiry_date=date(2027, 1, 1), status="ACTIVE")
    updated = apply_auto_expiry([rate], TODAY)
    assert updated[0].status == "ACTIVE"


def test_apply_auto_expiry_does_not_mutate_original():
    rate = make_rate(expiry_date=date(2026, 8, 1), status="ACTIVE")
    apply_auto_expiry([rate], TODAY)
    assert rate.status == "ACTIVE"