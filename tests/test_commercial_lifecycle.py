import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date, datetime
import pytest

from domain.entities import (
    Rfq, RfqParty, RfqCargoLine, RfqContainerRequirement, RfqSpecialRequirement,
    RfqMode, RfqServiceType, RfqStatus, PartyRole, Rate, RateVersion, RateLine,
    RateSurcharge, RateCategory, RateStatus, Route, RouteLeg, Quotation,
    QuotationOption, QuotationLine, ChargeCategory, QuotationStatus, Customer,
    CreditTier, MarginRule
)
from domain.in_memory_repos import (
    InMemoryRfqRepository, InMemoryRateRepository, InMemoryRouteRepository,
    InMemoryQuotationRepository, InMemoryCustomerRepository, InMemoryExchangeRateService,
    InMemoryEventPublisher, InMemoryMasterDataRepository
)
from domain.services.rfq_service import RfqService
from domain.services.rate_engine import RateEngine
from domain.services.route_service import RouteService, CommercialRouteEvaluation
from domain.services.quotation_service import QuotationService
from domain.services.acceptance_service import AcceptanceService
from calculations.air_freight import (
    Package, calculate_chargeable_weight, RateBreak, calculate_pivot_weight_optimization
)


TODAY = date(2026, 9, 2)


def test_air_pivot_weight_optimization():
    # 80 kg cargo at 45kg break rate $4.50/kg = $360.
    # At +100 kg break rate is $3.50/kg: 100 * 3.50 = $350.
    # Paying for 100 kg saves $10.0 (2.78%)!
    rate_breaks = [
        RateBreak(weight_break_kg=0, rate_per_kg=5.0),
        RateBreak(weight_break_kg=45, rate_per_kg=4.5),
        RateBreak(weight_break_kg=100, rate_per_kg=3.5),
        RateBreak(weight_break_kg=250, rate_per_kg=3.0),
    ]
    result = calculate_pivot_weight_optimization(actual_chargeable_weight=80.0, rate_breaks=rate_breaks)
    assert result.is_optimized is True
    assert result.optimized_weight_kg == 100.0
    assert result.optimized_total_cost == 350.0
    assert result.savings_amount == 10.0
    assert result.savings_pct == 2.78


def test_end_to_end_commercial_lifecycle():
    # 1. Setup in-memory environment
    rfq_repo = InMemoryRfqRepository()
    rate_repo = InMemoryRateRepository()
    route_repo = InMemoryRouteRepository()
    quote_repo = InMemoryQuotationRepository()
    cust_repo = InMemoryCustomerRepository()
    event_pub = InMemoryEventPublisher()
    fx_svc = InMemoryExchangeRateService()

    # 2. Seed Customer
    customer = Customer(
        customer_code="CUST-001",
        name="Al-Rahim Trading LLC",
        credit_limit_amount=100000.0,
        credit_tier=CreditTier.A,
    )
    cust_repo.save_customer(customer)
    cust_repo.set_exposure(customer.id, 10000.0)

    # 3. Seed 4-Tier Rates
    rate_line_40gp = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1500.0)
    baf_surcharge = RateSurcharge(
        charge_code="BAF",
        basis="PER_CONTAINER",
        amount=200.0,
        applicable_from=date(2026, 1, 1),
        applicable_to=date(2026, 12, 31),
    )
    rate_version = RateVersion(
        rate_id="RT-001",
        version_number=1,
        lines=[rate_line_40gp],
        surcharges=[baf_surcharge],
    )
    rate = Rate(
        rate_number="RT-SEA-2601",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="MAERSK",
        service_name="ME-Express",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        versions=[rate_version],
    )
    rate_repo.save_rate(rate)

    # 4. Seed Route
    route_leg = RouteLeg(
        from_location_id="PKKAR",
        to_location_id="AEJEA",
        carrier_id="MAERSK",
        transit_time_hours=48.0,
    )
    route = Route(
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode="SEA",
        legs=[route_leg],
    )
    route_repo.save_route(route)

    # 5. Capture & Validate RFQ
    rfq_svc = RfqService(rfq_repo=rfq_repo)
    rfq = Rfq(
        rfq_number="RFQ-2609-001",
        customer_id=customer.id,
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
        container_requirements=[RfqContainerRequirement(container_type_code="40GP", qty=1)],
        parties=[
            RfqParty(party_role=PartyRole.SHIPPER, name="Karachi Exporter"),
            RfqParty(party_role=PartyRole.CONSIGNEE, name="Dubai Importer"),
        ],
    )
    saved_rfq, val_result = rfq_svc.create_rfq(rfq, today=TODAY)
    assert val_result.is_valid is True
    assert saved_rfq.status == RfqStatus.SUBMITTED

    # Assign RFQ
    rfq_svc.assign_to_analyst(saved_rfq.id, "USER-PRICING-01")
    assert saved_rfq.status == RfqStatus.PRICING_IN_PROGRESS

    # 6. Automatic Rate Resolution & Charge Lines Generation
    rate_eng = RateEngine(rate_repo=rate_repo, fx_service=fx_svc)
    sel_rate, sel_version, lines, surcharges, reason = rate_eng.resolve_rate_for_lane(
        customer_id=customer.id,
        origin_id="PKKAR",
        destination_id="AEJEA",
        effective_date=TODAY,
        container_type="40GP",
    )
    assert sel_rate is not None
    assert len(lines) == 1
    assert len(surcharges) == 1

    charge_lines = rate_eng.calculate_freight_charge_lines(
        version=sel_version,
        matched_lines=lines,
        surcharges=surcharges,
        markup_pct=20.0,
        container_qty=1,
    )
    assert len(charge_lines) == 2  # Freight + BAF surcharge
    assert sum(cl.cost_amount for cl in charge_lines) == 1700.0  # 1500 + 200
    assert sum(cl.sell_amount for cl in charge_lines) == 2040.0  # (1500*1.2) + (200*1.2)

    # 7. Route Comparison
    route_svc = RouteService(route_repo=route_repo)
    routes = route_svc.discover_routes("PKKAR", "AEJEA", "SEA")
    assert len(routes) == 1
    evaluations = [
        CommercialRouteEvaluation(
            route=routes[0],
            total_landed_cost=1700.0,
            proposed_sell_price=2040.0,
            carrier_reliability_score=95.0,
            congestion_index=5.0,
            on_time_pct_trailing_12mo=98.0,
        )
    ]
    comp_result = route_svc.compare_evaluated_routes(evaluations, preferred_carrier_id="MAERSK")
    assert comp_result.cheapest is not None
    assert comp_result.customer_preferred is not None

    # 8. Multi-Option Quotation Generation with Margin Rule Evaluation
    quote_svc = QuotationService(quotation_repo=quote_repo, fx_service=fx_svc)
    opt_a = QuotationOption(
        label="Option A - Standard Sea FCL",
        charge_lines=charge_lines,
        route_id=routes[0].id,
        primary_rate_version_id=sel_version.id,
    )
    margin_rules = [
        MarginRule(
            service_type="FCL",
            min_margin_pct=10.0,
            customer_tier_overrides={"A": 8.0},
        )
    ]
    quotation = quote_svc.generate_quotation(
        rfq=saved_rfq,
        options=[opt_a],
        validity_days=14,
        margin_rules=margin_rules,
        customer_tier=customer.credit_tier.value,
        today=TODAY,
    )
    assert quotation.status == QuotationStatus.APPROVED  # Margin is 16.67% > 8.0%
    assert len(quotation.approvals) == 0
    assert opt_a.is_below_margin is False

    # 9. Quotation PDF Context Builder
    pdf_context = quote_svc.build_pdf_context(quotation, saved_rfq, customer)
    assert pdf_context["quotation_number"] == quotation.quotation_number
    assert len(pdf_context["options"]) == 1

    # Send to Customer
    quote_svc.send_to_customer(quotation.id)
    assert quotation.status == QuotationStatus.SENT_TO_CUSTOMER

    # 10. Customer Acceptance & Job Creation (5-point validation)
    accept_svc = AcceptanceService(
        quotation_repo=quote_repo,
        customer_repo=cust_repo,
        rate_repo=rate_repo,
        event_publisher=event_pub,
    )
    job_result = accept_svc.accept_quotation_and_create_job(
        quotation_id=quotation.id,
        selected_option_index=0,
        rfq=saved_rfq,
        branch_code="KHI",
        direction="EXP",
        today=TODAY,
        seq_num=147,
    )

    assert job_result.validation_result.is_valid is True
    assert job_result.job is not None
    assert job_result.job.job_number == "KHI-SEA-EXP-2609-00147"
    assert quotation.status == QuotationStatus.ACCEPTED
    assert len(job_result.estimated_revenue_lines) == 2
    assert len(job_result.estimated_cost_lines) == 2
    assert len(event_pub.published_events) == 1
    assert event_pub.published_events[0]["event"] == "booking.confirmed"
    assert event_pub.published_events[0]["payload"]["job_number"] == "KHI-SEA-EXP-2609-00147"


def test_quotation_below_margin_approval_trigger():
    quote_repo = InMemoryQuotationRepository()
    quote_svc = QuotationService(quotation_repo=quote_repo)

    thin_charge_lines = [
        QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=1000.0, sell_amount=1020.0),
    ]
    opt_thin = QuotationOption(label="Thin Margin Option", charge_lines=thin_charge_lines)
    rfq = Rfq(
        rfq_number="RFQ-2609-002",
        customer_id="CUST-002",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
        special_requirement=RfqSpecialRequirement(dgr_flag=True, dgr_un_number="UN1993", dgr_class="3"),
    )
    rules = [MarginRule(service_type="FCL", min_margin_pct=10.0)]
    quote = quote_svc.generate_quotation(rfq=rfq, options=[opt_thin], margin_rules=rules, today=TODAY)

    assert quote.status == QuotationStatus.PENDING_APPROVAL
    assert opt_thin.is_below_margin is True
    assert len(quote.approvals) == 2  # BELOW_MARGIN and DGR_COMPLIANCE
    assert any(a.approval_type == "BELOW_MARGIN" for a in quote.approvals)
    assert any(a.approval_type == "DGR_COMPLIANCE" for a in quote.approvals)

    # Sending should fail with pending approvals
    with pytest.raises(ValueError):
        quote_svc.send_to_customer(quote.id)


def test_quotation_revision_chaining():
    quote_repo = InMemoryQuotationRepository()
    quote_svc = QuotationService(quotation_repo=quote_repo)

    lines_v1 = [QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=1000.0, sell_amount=1200.0)]
    opt_v1 = QuotationOption(label="Option 1", charge_lines=lines_v1)
    rfq = Rfq(
        rfq_number="RFQ-2609-003",
        customer_id="CUST-003",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
    )
    quote_v1 = quote_svc.generate_quotation(rfq=rfq, options=[opt_v1], today=TODAY)

    lines_v2 = [QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=950.0, sell_amount=1150.0)]
    opt_v2 = QuotationOption(label="Option 1 Revised", charge_lines=lines_v2)
    quote_v2 = quote_svc.revise_quotation(parent_quotation_id=quote_v1.id, new_options=[opt_v2], rfq=rfq, today=TODAY)

    assert quote_v1.status == QuotationStatus.REVISED
    assert quote_v2.parent_quotation_id == quote_v1.id


def test_customer_acceptance_credit_block():
    quote_repo = InMemoryQuotationRepository()
    cust_repo = InMemoryCustomerRepository()
    accept_svc = AcceptanceService(quotation_repo=quote_repo, customer_repo=cust_repo)

    customer = Customer(
        customer_code="CUST-004",
        name="High Risk Customer",
        credit_limit_amount=5000.0,
        credit_tier=CreditTier.C,
    )
    cust_repo.save_customer(customer)
    cust_repo.set_exposure(customer.id, 4000.0)

    lines = [QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=1500.0, sell_amount=2000.0)]
    opt = QuotationOption(label="Option 1", charge_lines=lines)
    rfq = Rfq(
        rfq_number="RFQ-2609-004",
        customer_id=customer.id,
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
    )
    quotation = Quotation(
        quotation_number="QT-2609-004",
        rfq_id=rfq.id,
        expiry_date=date(2026, 9, 20),
        options=[opt],
    )
    quote_repo.save_quotation(quotation)

    job_result = accept_svc.accept_quotation_and_create_job(
        quotation_id=quotation.id,
        selected_option_index=0,
        rfq=rfq,
        today=TODAY,
    )

    assert job_result.validation_result.is_valid is False
    assert job_result.job is None
    assert any("Credit limit exceeded" in e for e in job_result.validation_result.errors)


def test_multi_carrier_comparison_and_ranking():
    rate_repo = InMemoryRateRepository()
    rate_eng = RateEngine(rate_repo=rate_repo)

    # Carrier 1: Maersk ($1500 + $200 BAF = $1700)
    r1_line = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1500.0)
    r1_sur = RateSurcharge(charge_code="BAF", basis="PER_CONTAINER", amount=200.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))
    r1_v = RateVersion(rate_id="R1", version_number=1, lines=[r1_line], surcharges=[r1_sur])
    r1 = Rate(rate_number="RT-MAERSK", rate_type="SEA", rate_category=RateCategory.FAK, carrier_vendor_id="MAERSK", service_name="Maersk ME", origin_location_id="PKKAR", destination_location_id="AEJEA", effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), versions=[r1_v])
    rate_repo.save_rate(r1)

    # Carrier 2: CMA CGM ($1200 + $250 BAF = $1450 - Cheapest)
    r2_line = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1200.0)
    r2_sur = RateSurcharge(charge_code="BAF", basis="PER_CONTAINER", amount=250.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))
    r2_v = RateVersion(rate_id="R2", version_number=1, lines=[r2_line], surcharges=[r2_sur])
    r2 = Rate(rate_number="RT-CMACGM", rate_type="SEA", rate_category=RateCategory.FAK, carrier_vendor_id="CMA_CGM", service_name="CMA Express", origin_location_id="PKKAR", destination_location_id="AEJEA", effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), versions=[r2_v])
    rate_repo.save_rate(r2)

    # Carrier 3: MSC ($1600 + $300 BAF = $1900)
    r3_line = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1600.0)
    r3_sur = RateSurcharge(charge_code="BAF", basis="PER_CONTAINER", amount=300.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))
    r3_v = RateVersion(rate_id="R3", version_number=1, lines=[r3_line], surcharges=[r3_sur])
    r3 = Rate(rate_number="RT-MSC", rate_type="SEA", rate_category=RateCategory.FAK, carrier_vendor_id="MSC", service_name="MSC Gulf", origin_location_id="PKKAR", destination_location_id="AEJEA", effective_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31), versions=[r3_v])
    rate_repo.save_rate(r3)

    results = rate_eng.compare_all_carriers_on_lane(
        customer_id="CUST-1",
        origin_id="PKKAR",
        destination_id="AEJEA",
        effective_date=TODAY,
        container_type="40GP",
        container_qty=1,
        markup_pct=20.0,
    )

    assert len(results) == 3
    # Sorted cheapest first
    assert results[0].carrier_id == "CMA_CGM"
    assert results[0].total_landed_cost == 1450.0
    assert results[1].carrier_id == "MAERSK"
    assert results[1].total_landed_cost == 1700.0
    assert results[2].carrier_id == "MSC"
    assert results[2].total_landed_cost == 1900.0


def test_multi_currency_rate_conversion():
    rate_repo = InMemoryRateRepository()
    fx_svc = InMemoryExchangeRateService()  # 1 EUR = 1.08 USD
    rate_eng = RateEngine(rate_repo=rate_repo, fx_service=fx_svc)

    line = RateLine(charge_code="AFT", rate_basis="PER_KG", amount=5.0)  # 5.0 EUR/kg
    sur = RateSurcharge(charge_code="FSC", basis="PER_KG", amount=1.0, applicable_from=date(2026, 1, 1), applicable_to=date(2026, 12, 31))  # 1.0 EUR/kg
    version = RateVersion(rate_id="R-EUR", version_number=1, lines=[line], surcharges=[sur])
    rate = Rate(
        rate_number="RT-AIR-EUR",
        rate_type="AIR",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="LUFTHANSA",
        service_name="LH-Cargo",
        origin_location_id="PKKAR",
        destination_location_id="DEHAM",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        currency_code="EUR",
        versions=[version],
    )
    rate_repo.save_rate(rate)

    charge_lines = rate_eng.calculate_freight_charge_lines(
        version=version,
        matched_lines=[line],
        surcharges=[sur],
        markup_pct=10.0,
        rate_currency="EUR",
        target_currency="USD",
        effective_date=TODAY,
        weight_kg=100.0,
    )

    # 100 kg * 5 EUR = 500 EUR -> 500 * 1.08 = 540 USD cost. Sell = 540 * 1.1 = 594 USD
    # 100 kg * 1 EUR = 100 EUR -> 100 * 1.08 = 108 USD cost. Sell = 108 * 1.1 = 118.8 USD
    assert len(charge_lines) == 2
    assert charge_lines[0].cost_amount == 540.0
    assert charge_lines[0].sell_amount == 594.0
    assert charge_lines[1].cost_amount == 108.0
    assert charge_lines[1].sell_amount == 118.8


def test_route_discovery_transshipment_combination():
    route_repo = InMemoryRouteRepository()
    route_svc = RouteService(route_repo=route_repo)

    available_legs = [
        RouteLeg(from_location_id="PKKAR", to_location_id="AEDXB", carrier_id="EMIRATES", transit_time_hours=4.0),
        RouteLeg(from_location_id="AEDXB", to_location_id="SAJED", carrier_id="SAUDIA", transit_time_hours=3.5),
        RouteLeg(from_location_id="PKKAR", to_location_id="USNYC", carrier_id="QATAR", transit_time_hours=18.0),
    ]

    discovered = route_svc.discover_routes("PKKAR", "SAJED", "AIR", available_legs=available_legs)
    assert len(discovered) == 1
    route = discovered[0]
    assert len(route.legs) == 2
    assert route.total_transit_hours == 7.5
    assert route.transshipment_count == 1
    assert route.legs[0].to_location_id == "AEDXB"
    assert route.legs[1].from_location_id == "AEDXB"


def test_html_quotation_rendering():
    quote_repo = InMemoryQuotationRepository()
    quote_svc = QuotationService(quotation_repo=quote_repo)

    customer = Customer(customer_code="CUST-005", name="Pak Textiles Ltd.", credit_limit_amount=50000.0)
    rfq = Rfq(
        rfq_number="RFQ-2609-005",
        customer_id=customer.id,
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
    )
    lines = [
        QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=1500.0, sell_amount=1800.0, description="Ocean Freight 40GP"),
        QuotationLine(charge_code="BAF", category=ChargeCategory.SURCHARGE, cost_amount=200.0, sell_amount=240.0, description="Bunker Adjustment Factor"),
    ]
    opt = QuotationOption(label="Option A - Standard Sea FCL", charge_lines=lines)
    quote = quote_svc.generate_quotation(rfq=rfq, options=[opt], today=TODAY)

    html_content = quote_svc.render_html_quotation(quotation=quote, rfq=rfq, customer=customer)
    assert "<!DOCTYPE html>" in html_content
    assert "COMMERCIAL QUOTATION" in html_content
    assert quote.quotation_number in html_content
    assert "Pak Textiles Ltd." in html_content
    assert "$1800.00" in html_content
    assert "Inter-Fret Consolidators (Pvt.) Ltd." in html_content
