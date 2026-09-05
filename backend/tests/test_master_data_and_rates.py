"""
Team 2 Phase 2 Comprehensive Test Suite:
Master Data, Rate/Tariff Engine, Rate Versioning, Immutability, FX Locking, Bulk Import, and Expiry.
"""

from datetime import date, timedelta
import pytest

from domain.entities import (
    Country, Location, Zone, Carrier, Vessel, VesselSchedule, FlightSchedule,
    ContainerType, Commodity, Customer, CustomerContact, CustomerAddress,
    CreditTier, Vendor, Agent, AgentRateAgreement, Rate, RateVersion, RateLine,
    RateSurcharge, RateCategory, RateStatus, Quotation, QuotationOption,
    QuotationLine, ChargeCategory, QuotationStatus
)
from domain.in_memory_repos import (
    InMemoryMasterDataRepository, InMemoryCustomerRepository,
    InMemoryRateRepository, InMemoryExchangeRateService, InMemoryEventPublisher,
    InMemoryQuotationRepository
)
from domain.services.master_data_service import MasterDataService
from domain.services.fx_service import FxService
from domain.services.rate_version_service import RateVersionService
from domain.services.rate_importer import RateImporterService
from domain.services.rate_expiry_service import RateExpiryService
from domain.services.rate_engine import RateEngine


TODAY = date(2026, 9, 2)


# =============================================================================
# 1. Master Data Lookups & Customer Master
# =============================================================================

def test_master_data_lookups_and_seeding():
    master_repo = InMemoryMasterDataRepository()
    cust_repo = InMemoryCustomerRepository()
    md_svc = MasterDataService(master_repo=master_repo, customer_repo=cust_repo)

    # Seed catalogs
    md_svc.seed_standard_catalogs()

    # Container types
    c20 = md_svc.get_container_type("20GP")
    assert c20 is not None
    assert c20.cbm_capacity == 33.2
    assert c20.max_payload_kg == 28200

    c40hc = md_svc.get_container_type("40HC")
    assert c40hc is not None
    assert c40hc.cbm_capacity == 76.3

    # Add countries
    md_svc.add_country(Country(iso_code="PK", name="Pakistan", region="South Asia", trade_zone="SAARC"))
    md_svc.add_country(Country(iso_code="IR", name="Iran", region="Middle East", is_sanctioned=True))

    assert md_svc.is_country_sanctioned("PK") is False
    assert md_svc.is_country_sanctioned("IR") is True

    # Add locations and test typeahead search
    l1 = Location(un_locode="PKKAR", name="Karachi Port", city="Karachi", type="SEA_PORT")
    l2 = Location(un_locode="PKKHI", iata_code="KHI", name="Jinnah International Airport", city="Karachi", type="AIRPORT")
    l3 = Location(un_locode="AEJEA", name="Jebel Ali Port", city="Dubai", type="SEA_PORT")
    md_svc.add_location(l1)
    md_svc.add_location(l2)
    md_svc.add_location(l3)

    search_res = md_svc.search_locations("karachi")
    assert len(search_res) == 2

    search_air = md_svc.search_locations("karachi", loc_type="AIRPORT")
    assert len(search_air) == 1
    assert search_air[0].iata_code == "KHI"


def test_customer_registration_credit_position_and_override():
    master_repo = InMemoryMasterDataRepository()
    cust_repo = InMemoryCustomerRepository()
    md_svc = MasterDataService(master_repo=master_repo, customer_repo=cust_repo)

    cust1 = md_svc.register_customer(
        name="Al-Rahim Trading Co.",
        credit_limit_amount=100000.0,
        credit_tier=CreditTier.A,
        payment_terms_days=45,
    )
    assert cust1.customer_code == "CUST-0001"

    cust2 = md_svc.register_customer(
        name="Indus Textiles",
        credit_limit_amount=50000.0,
        credit_tier=CreditTier.B,
    )
    assert cust2.customer_code == "CUST-0002"

    # Set exposure and check credit position
    cust_repo.set_exposure(cust1.id, 65000.0)
    pos = md_svc.get_customer_credit_position(cust1.id)
    assert pos["credit_limit"] == 100000.0
    assert pos["total_exposure"] == 65000.0
    assert pos["available_credit"] == 35000.0
    assert pos["is_blocked"] is False

    # Grant credit override
    override = md_svc.grant_credit_override(
        customer_id=cust1.id,
        reason="Seasonal textile volume surge",
        approved_by="FINANCE_CONTROLLER",
        valid_from=TODAY,
        valid_to=TODAY + timedelta(days=30),
    )
    assert override.customer_id == cust1.id
    assert override.approved_by == "FINANCE_CONTROLLER"


# =============================================================================
# 2. FX Multi-Currency & Rate Locking
# =============================================================================

def test_fx_conversion_and_locking():
    fx_svc = FxService()

    # 1 EUR = 1.08 USD, 1 USD = 1.0 USD
    converted_usd = fx_svc.convert(100.0, from_currency="EUR", to_currency="USD")
    assert converted_usd == 108.0

    # Lock rate at quotation time (e.g. quote Q-101 locked at 1 EUR = 1.08 USD)
    locked = fx_svc.lock_exchange_rate(
        quotation_id="Q-101",
        from_currency="EUR",
        to_currency="USD",
        effective_date=TODAY,
    )
    assert locked.locked_rate == 1.08

    # Later market exchange rate fluctuates (EUR drops to 1.05 USD)
    fx_svc.set_rate_to_usd("EUR", 1.05)

    # Conversion using quotation ID uses frozen rate (1.08)
    frozen_val = fx_svc.convert(100.0, from_currency="EUR", to_currency="USD", quotation_id="Q-101")
    assert frozen_val == 108.0

    # Conversion without quotation ID uses current floating rate (1.05)
    floating_val = fx_svc.convert(100.0, from_currency="EUR", to_currency="USD")
    assert floating_val == 105.0

    # Check FX variance
    variance = fx_svc.calculate_fx_variance(100.0, "EUR", "USD", quotation_id="Q-101")
    assert variance.locked_value == 108.0
    assert variance.current_value == 105.0
    assert variance.variance_amount == 3.0
    assert variance.is_gain is False  # Value dropped compared to locked rate


# =============================================================================
# 3. Rate Versioning, Immutability & Side-by-Side Comparison
# =============================================================================

def test_rate_version_immutability_and_diff():
    rate_repo = InMemoryRateRepository()
    ver_svc = RateVersionService(rate_repo=rate_repo)

    # 1. Create Rate V1
    line_v1 = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1400.0)
    sur_v1 = RateSurcharge(charge_code="BAF", basis="PER_CONTAINER", amount=200.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))

    rate = ver_svc.create_rate(
        rate_number="RT-MAERSK-PKAE",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="MAERSK",
        service_name="Middle East Express",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        lines=[line_v1],
        surcharges=[sur_v1],
    )

    assert len(rate.versions) == 1
    v1 = rate.versions[0]
    assert v1.version_number == 1
    assert v1.lines[0].amount == 1400.0

    # 2. Modify rate by creating Version 2 (V1 MUST REMAIN UNTOUCHED)
    line_v2 = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1550.0)
    line_v2_new = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="20GP", amount=900.0)
    sur_v2 = RateSurcharge(charge_code="BAF", basis="PER_CONTAINER", amount=250.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))

    v2 = ver_svc.create_new_rate_version(
        rate_id=rate.id,
        new_lines=[line_v2, line_v2_new],
        new_surcharges=[sur_v2],
        modified_by="ANALYST_AHMED",
        reason="General rate increase (GRI) Q3",
    )

    assert len(rate.versions) == 2
    assert v2.version_number == 2

    # Verify V1 remains unchanged (Immutability check)
    v1_reloaded = rate.versions[0]
    assert v1_reloaded.lines[0].amount == 1400.0
    assert v1_reloaded.surcharges[0].amount == 200.0
    assert len(v1_reloaded.lines) == 1

    # Verify V2 has updated lines
    v2_reloaded = rate.versions[1]
    assert v2_reloaded.lines[0].amount == 1550.0
    assert len(v2_reloaded.lines) == 2

    # 3. Compare Version 1 vs Version 2
    diff = ver_svc.compare_rate_versions(rate.id, v1_number=1, v2_number=2)
    assert len(diff.added_lines) == 1
    assert diff.added_lines[0].container_type_code == "20GP"
    assert len(diff.modified_lines) == 1
    assert diff.modified_lines[0]["v1_amount"] == 1400.0
    assert diff.modified_lines[0]["v2_amount"] == 1550.0
    assert diff.modified_lines[0]["change"] == 150.0
    assert len(diff.modified_surcharges) == 1
    assert diff.modified_surcharges[0]["v1_amount"] == 200.0
    assert diff.modified_surcharges[0]["v2_amount"] == 250.0


# =============================================================================
# 4. Weight-Break & Container-Specific Rate Resolution
# =============================================================================

def test_air_freight_weight_break_resolution():
    rate_repo = InMemoryRateRepository()
    rate_eng = RateEngine(rate_repo=rate_repo)

    lines = [
        RateLine(charge_code="AFT", rate_basis="PER_KG", weight_break_from=0, weight_break_to=45, amount=6.0),
        RateLine(charge_code="AFT", rate_basis="PER_KG", weight_break_from=45, weight_break_to=100, amount=4.8),
        RateLine(charge_code="AFT", rate_basis="PER_KG", weight_break_from=100, weight_break_to=250, amount=4.0),
        RateLine(charge_code="AFT", rate_basis="PER_KG", weight_break_from=250, weight_break_to=500, amount=3.5),
        RateLine(charge_code="AFT", rate_basis="PER_KG", weight_break_from=500, weight_break_to=None, amount=3.0),
    ]
    surcharges = [
        RateSurcharge(charge_code="FSC", basis="PER_KG", amount=0.8, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31)),
        RateSurcharge(charge_code="AWB", basis="FLAT", amount=25.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31)),
    ]
    version = RateVersion(rate_id="R-AIR-1", version_number=1, lines=lines, surcharges=surcharges)
    rate = Rate(
        rate_number="RT-EK-CARGO",
        rate_type="AIR",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="EMIRATES",
        service_name="EK SkyCargo Priority",
        origin_location_id="PKKHI",
        destination_location_id="AEDXB",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        versions=[version],
    )
    rate_repo.save_rate(rate)

    # Test 120 kg shipment (matches 100-250 kg break @ $4.0/kg)
    r, v, matched_lines, matched_surcharges, _ = rate_eng.resolve_rate_for_lane(
        customer_id="CUST-1",
        origin_id="PKKHI",
        destination_id="AEDXB",
        effective_date=TODAY,
        weight_kg=120.0,
    )
    assert r is not None
    assert len(matched_lines) == 1
    assert matched_lines[0].amount == 4.0
    assert len(matched_surcharges) == 2

    # Calculate quotation lines
    quote_lines = rate_eng.calculate_freight_charge_lines(
        version=v,
        matched_lines=matched_lines,
        surcharges=matched_surcharges,
        weight_kg=120.0,
        markup_pct=15.0,
    )
    # Freight: 120 * $4.0 = $480 cost -> $552 sell
    # FSC: 120 * $0.8 = $96 cost -> $110.4 sell
    # AWB: $25 flat -> $28.75 sell
    assert quote_lines[0].cost_amount == 480.0
    assert quote_lines[0].sell_amount == 552.0
    assert quote_lines[1].cost_amount == 96.0
    assert quote_lines[1].sell_amount == 110.4
    assert quote_lines[2].cost_amount == 25.0
    assert quote_lines[2].sell_amount == 28.75


# =============================================================================
# 5. Bulk Rate CSV Import with Dry-Run & Row-Level Errors
# =============================================================================

def test_rate_bulk_csv_import_validation_and_dry_run():
    rate_repo = InMemoryRateRepository()
    master_repo = InMemoryMasterDataRepository()
    master_repo.add_location(Location(un_locode="PKKAR", name="Karachi Port", city="Karachi", type="SEA_PORT"))
    master_repo.add_location(Location(un_locode="AEJEA", name="Jebel Ali Port", city="Dubai", type="SEA_PORT"))

    importer = RateImporterService(rate_repo=rate_repo, master_repo=master_repo)

    # CSV with 1 valid row, 1 row with invalid category, 1 row with invalid dates, 1 row with unknown port
    csv_data = """carrier_code,service_name,origin_code,dest_code,rate_type,rate_category,effective_date,expiry_date,currency,charge_code,rate_basis,amount,container_type_code
MAERSK,Direct ME,PKKAR,AEJEA,SEA,FAK,2026-09-01,2026-12-31,USD,OFT,PER_CONTAINER,1450.0,40GP
CMA_CGM,Express ME,PKKAR,AEJEA,SEA,INVALID_CAT,2026-09-01,2026-12-31,USD,OFT,PER_CONTAINER,1350.0,40GP
HAPAG,Gulf Line,PKKAR,AEJEA,SEA,FAK,2026-12-31,2026-01-01,USD,OFT,PER_CONTAINER,1400.0,40GP
MSC,Red Sea,PKKAR,UNKNOWN_PORT,SEA,FAK,2026-09-01,2026-12-31,USD,OFT,PER_CONTAINER,1500.0,40GP
"""

    # Dry run mode
    report_preview = importer.import_rates_from_csv(csv_data, dry_run=True)
    assert report_preview.total_rows == 4
    assert report_preview.error_count == 3
    assert report_preview.success_count == 1
    assert report_preview.is_successful is False
    assert len(report_preview.created_rate_ids) == 0  # Dry run creates nothing

    # Verify specific row-level errors
    errs = report_preview.row_errors
    assert any(e.row_number == 2 and e.field == "rate_category" for e in errs)
    assert any(e.row_number == 3 and e.field == "expiry_date" for e in errs)
    assert any(e.row_number == 4 and "UNKNOWN_PORT" in e.error_message for e in errs)

    # Clean CSV with valid data only (Commit mode)
    clean_csv = """carrier_code,service_name,origin_code,dest_code,rate_type,rate_category,effective_date,expiry_date,currency,charge_code,rate_basis,amount,container_type_code
MAERSK,Direct ME,PKKAR,AEJEA,SEA,FAK,2026-09-01,2026-12-31,USD,OFT,PER_CONTAINER,1450.0,40GP
CMA_CGM,Express ME,PKKAR,AEJEA,SEA,PROMOTIONAL,2026-09-01,2026-12-31,USD,OFT,PER_CONTAINER,1350.0,40GP
"""
    report_commit = importer.import_rates_from_csv(clean_csv, dry_run=False)
    assert report_commit.total_rows == 2
    assert report_commit.error_count == 0
    assert report_commit.is_successful is True
    assert len(report_commit.created_rate_ids) == 2

    # Verify rates are saved in repository
    saved_rates = rate_repo.find_rates(origin_id="PKKAR", destination_id="AEJEA", effective_date=TODAY)
    assert len(saved_rates) == 2


# =============================================================================
# 6. Rate Expiry Monitoring & Alerts
# =============================================================================

def test_rate_expiry_monitoring_and_auto_expiration():
    rate_repo = InMemoryRateRepository()
    event_pub = InMemoryEventPublisher()
    expiry_svc = RateExpiryService(rate_repo=rate_repo, event_publisher=event_pub)

    # Rate 1: Expiring in 2 days (3-day escalation)
    r1 = Rate(
        rate_number="RT-EXP-2D",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="MAERSK",
        service_name="Service 1",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 8, 1),
        expiry_date=TODAY + timedelta(days=2),
        status=RateStatus.ACTIVE,
    )
    rate_repo.save_rate(r1)

    # Rate 2: Expiring in 6 days (7-day warning)
    r2 = Rate(
        rate_number="RT-EXP-6D",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="MSC",
        service_name="Service 2",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 8, 1),
        expiry_date=TODAY + timedelta(days=6),
        status=RateStatus.ACTIVE,
    )
    rate_repo.save_rate(r2)

    # Rate 3: Expired yesterday (Auto-expiration)
    r3 = Rate(
        rate_number="RT-ALREADY-EXP",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="CMA",
        service_name="Service 3",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 8, 1),
        expiry_date=TODAY - timedelta(days=1),
        status=RateStatus.ACTIVE,
    )
    rate_repo.save_rate(r3)

    # Run daily check
    report = expiry_svc.run_daily_expiry_check(reference_date=TODAY)
    assert report.total_active_checked == 3
    assert report.escalation_3_day_count == 1
    assert report.warning_7_day_count == 1
    assert report.expired_count == 1
    assert r3.id in report.auto_expired_rate_ids

    # Verify R3 status auto-updated to EXPIRED
    assert r3.status == RateStatus.EXPIRED

    # Verify event published
    assert len(event_pub.published_events) == 1
    assert event_pub.published_events[0]["event"] == "rate.expiry_check_completed"

    # Verify quotation validation warning for expired rate
    v3 = RateVersion(rate_id=r3.id, version_number=1)
    r3.versions.append(v3)
    rate_repo.save_rate(r3)

    opt = QuotationOption(label="Option with Expired Rate", primary_rate_version_id=v3.id)
    quote = Quotation(quotation_number="QT-TEST", rfq_id="RFQ-1", expiry_date=TODAY + timedelta(days=10), options=[opt])

    warnings = expiry_svc.validate_quotation_rate_versions(quote, reference_date=TODAY)
    assert len(warnings) == 1
    assert "RT-ALREADY-EXP" in warnings[0]
