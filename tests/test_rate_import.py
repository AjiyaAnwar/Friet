import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rate_engine.import_service import validate_rate_rows

KNOWN_LOCATIONS = {"LOC-KHI", "LOC-DXB"}
KNOWN_CARRIERS = {"CAR-MAERSK"}


def valid_row(**overrides):
    defaults = dict(
        rate_number="RT-001", rate_type="OCEAN_FREIGHT", rate_category="FAK",
        carrier_vendor_id="CAR-MAERSK", origin_location_id="LOC-KHI",
        destination_location_id="LOC-DXB", effective_date="2026-01-01",
        expiry_date="2026-12-31", currency_code="USD",
    )
    defaults.update(overrides)
    return defaults


def test_all_valid_rows_pass():
    rows = [valid_row(), valid_row(rate_number="RT-002")]
    report = validate_rate_rows(rows, KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.success_count == 2
    assert report.error_count == 0
    assert report.total_rows == 2


def test_missing_required_field_reported():
    row = valid_row()
    del row["currency_code"]
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert any("currency_code" in e for e in report.row_errors[0].errors)


def test_invalid_date_format_reported():
    row = valid_row(effective_date="01/01/2026")
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert any("effective_date" in e for e in report.row_errors[0].errors)


def test_effective_after_expiry_reported():
    row = valid_row(effective_date="2026-12-31", expiry_date="2026-01-01")
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert any("on or before" in e for e in report.row_errors[0].errors)


def test_unknown_location_reported():
    row = valid_row(origin_location_id="LOC-NOWHERE")
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert any("Unknown origin_location_id" in e for e in report.row_errors[0].errors)


def test_unknown_carrier_reported():
    row = valid_row(carrier_vendor_id="CAR-UNKNOWN")
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert any("Unknown carrier_vendor_id" in e for e in report.row_errors[0].errors)


def test_duplicate_rate_number_within_batch_reported():
    rows = [valid_row(rate_number="RT-DUP"), valid_row(rate_number="RT-DUP")]
    report = validate_rate_rows(rows, KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.error_count == 1
    assert report.success_count == 1


def test_multiple_errors_on_same_row_all_reported():
    row = valid_row(origin_location_id="BAD", carrier_vendor_id="ALSO_BAD")
    del row["currency_code"]
    report = validate_rate_rows([row], KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert len(report.row_errors[0].errors) == 3


def test_dry_run_flag_is_preserved_and_does_not_persist():
    report = validate_rate_rows([valid_row()], KNOWN_LOCATIONS, KNOWN_CARRIERS, dry_run=True)
    assert report.dry_run is True
    assert len(report.valid_rows) == 1


def test_row_numbers_are_1_indexed_and_track_position():
    rows = [valid_row(), valid_row(rate_number="")]
    report = validate_rate_rows(rows, KNOWN_LOCATIONS, KNOWN_CARRIERS)
    assert report.row_errors[0].row_number == 2