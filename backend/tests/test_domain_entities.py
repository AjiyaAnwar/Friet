import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import date, datetime, time
from domain.entities import (
    Country, Location, Zone, Currency, ExchangeRate, Incoterm, ContainerType,
    Commodity, PackageType, UldType, ChargeCode, DocumentType, Carrier,
    Vessel, VesselSchedule, FlightSchedule, Customer, CustomerContact,
    CustomerAddress, CustomerPortalUser, CustomerCreditOverride, CreditTier,
    Vendor, Agent, AgentRateAgreement, Rate, RateVersion, RateLine,
    RateSurcharge, RateCategory, RateStatus, RateVersionApprovalStatus,
    MarginRule, Rfq, RfqParty, RfqCargoLine, RfqContainerRequirement,
    RfqSpecialRequirement, RfqMode, RfqServiceType, RfqStatus, PartyRole,
    Route, RouteLeg, Quotation, QuotationOption, QuotationLine, ChargeCategory,
    QuotationStatus, QuotationApproval, Job
)


def test_master_data_entities_instantiation():
    country = Country(iso_code="PK", name="Pakistan", region="Asia", trade_zone="SAARC")
    assert country.iso_code == "PK"
    assert country.is_sanctioned is False

    loc = Location(un_locode="PKKAR", name="Karachi Port", country_id=country.id, city="Karachi", type="SEA_PORT")
    assert loc.un_locode == "PKKAR"
    assert loc.type == "SEA_PORT"

    curr = Currency(code="USD", name="US Dollar", symbol="$")
    assert curr.code == "USD"

    fx = ExchangeRate(currency_code="USD", rate_date=date(2026, 9, 2), rate_to_base=1.0)
    assert fx.rate_to_base == 1.0

    ct = ContainerType(code="40HC", cbm_capacity=76.3, max_payload_kg=26500)
    assert ct.code == "40HC"

    comm = Commodity(hs_code="847130", name="Laptops", is_dgr=False)
    assert comm.hs_code == "847130"


def test_customer_and_vendor_entities():
    cust = Customer(
        customer_code="CUST-001",
        name="Al-Rahim Trading",
        credit_limit_amount=50000.0,
        credit_tier=CreditTier.A,
    )
    assert cust.customer_code == "CUST-001"
    assert cust.credit_tier == CreditTier.A

    contact = CustomerContact(customer_id=cust.id, name="Ahmed Ali", role="Logistics Manager", email="ahmed@example.com")
    assert contact.customer_id == cust.id

    vendor = Vendor(vendor_code="VEND-001", name="Maersk Line", vendor_type="SHIPPING_LINE")
    assert vendor.vendor_code == "VEND-001"


def test_four_tier_rate_hierarchy():
    line = RateLine(charge_code="OFT", rate_basis="PER_CONTAINER", container_type_code="40GP", amount=1200.0)
    surcharge = RateSurcharge(
        charge_code="BAF",
        basis="PER_CONTAINER",
        amount=150.0,
        applicable_from=date(2026, 1, 1),
        applicable_to=date(2026, 12, 31),
    )
    version = RateVersion(rate_id="R1", version_number=1, lines=[line], surcharges=[surcharge])
    rate = Rate(
        rate_number="RT-SEA-2601",
        rate_type="SEA",
        rate_category=RateCategory.FAK,
        carrier_vendor_id="VEND-001",
        service_name="Middle East Express",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        effective_date=date(2026, 1, 1),
        expiry_date=date(2026, 12, 31),
        versions=[version],
    )

    assert rate.current_version is not None
    assert rate.current_version.version_number == 1
    assert len(rate.current_version.lines) == 1
    assert len(rate.current_version.surcharges) == 1
    assert rate.current_version.lines[0].amount == 1200.0


def test_rfq_hierarchy():
    party = RfqParty(party_role=PartyRole.SHIPPER, name="Karachi Textiles")
    cargo = RfqCargoLine(packages=10, gross_weight=500.0, volume_cbm=2.5, dimensions_length_cm=50, dimensions_width_cm=40, dimensions_height_cm=30)
    container_req = RfqContainerRequirement(container_type_code="40GP", qty=2, weight_per_container=15000.0)
    special_req = RfqSpecialRequirement(dgr_flag=False, lc_flag=True, lc_number="LC123456")

    rfq = Rfq(
        rfq_number="RFQ-2609-001",
        customer_id="CUST-001",
        origin_location_id="PKKAR",
        destination_location_id="AEJEA",
        mode=RfqMode.SEA,
        service_type=RfqServiceType.FCL,
        cargo_ready_date=date(2026, 9, 5),
        preferred_departure=date(2026, 9, 10),
        required_delivery=date(2026, 9, 20),
        parties=[party],
        cargo_lines=[cargo],
        container_requirements=[container_req],
        special_requirement=special_req,
    )

    assert len(rfq.parties) == 1
    assert len(rfq.cargo_lines) == 1
    assert len(rfq.container_requirements) == 1
    assert rfq.special_requirement.lc_number == "LC123456"


def test_quotation_hierarchy_and_derived_properties():
    line1 = QuotationLine(charge_code="OFT", category=ChargeCategory.FREIGHT, cost_amount=1000.0, sell_amount=1200.0)
    line2 = QuotationLine(charge_code="BAF", category=ChargeCategory.SURCHARGE, cost_amount=100.0, sell_amount=120.0)
    option = QuotationOption(label="Option A - Direct", charge_lines=[line1, line2])

    assert option.total_cost == 1100.0
    assert option.total_sell == 1320.0
    assert option.gross_margin == 220.0
    assert option.margin_pct == 16.67

    quotation = Quotation(
        quotation_number="QT-2609-001",
        rfq_id="RFQ-001",
        expiry_date=date(2026, 9, 20),
        options=[option],
    )
    assert len(quotation.options) == 1
    assert quotation.status == QuotationStatus.DRAFT
