"""
Master Data & Reference Service (Team 2 - Phase 2).

Provides lookup, CRUD, search, and typeahead for:
- Geographic Master (Country, Location, Zone)
- Carrier & Network Master (Carrier, Vessel, VesselSchedule, FlightSchedule)
- Customer & Vendor Master (Customer, Contact, Address, Credit Override, Vendor, Agent, AgentRateAgreement)
- Reference Data (Incoterms, ContainerTypes, Commodities, PackageTypes, UldTypes, ChargeCodes, DocumentTypes)
"""

from __future__ import annotations

from datetime import date
from typing import Any
from domain.entities import (
    Country, Location, Zone, Currency, Incoterm, ContainerType,
    Commodity, PackageType, UldType, ChargeCode, DocumentType,
    Carrier, Vessel, VesselSchedule, FlightSchedule, Customer,
    CustomerContact, CustomerAddress, CustomerCreditOverride, CreditTier,
    Vendor, Agent, AgentRateAgreement
)
from domain.interfaces import MasterDataRepositoryPort, CustomerRepositoryPort


class MasterDataService:
    def __init__(
        self,
        master_repo: Any,
        customer_repo: CustomerRepositoryPort | None = None,
    ) -> None:
        self.master_repo = master_repo
        self.customer_repo = customer_repo

    # =========================================================================
    # Geographic Master Data (SRS Section 2.1)
    # =========================================================================

    def add_country(self, country: Country) -> Country:
        if hasattr(self.master_repo, "add_country"):
            self.master_repo.add_country(country)
        return country

    def get_country(self, iso_code: str) -> Country | None:
        if hasattr(self.master_repo, "get_country"):
            return self.master_repo.get_country(iso_code)
        return None

    def is_country_sanctioned(self, iso_code: str) -> bool:
        country = self.get_country(iso_code)
        return country.is_sanctioned if country else False

    def add_location(self, location: Location) -> Location:
        if hasattr(self.master_repo, "add_location"):
            self.master_repo.add_location(location)
        return location

    def get_location(self, location_id_or_code: str) -> Location | None:
        return self.master_repo.get_location_by_id(location_id_or_code)

    def search_locations(
        self,
        query: str,
        loc_type: str | None = None,
        is_active_only: bool = True,
    ) -> list[Location]:
        """
        Typeahead search for port/airport by name, city, UN/LOCODE, or IATA code.
        """
        if hasattr(self.master_repo, "search_locations"):
            return self.master_repo.search_locations(query, loc_type, is_active_only)
        return []

    # =========================================================================
    # Carrier & Network Master (SRS Section 2.2)
    # =========================================================================

    def add_carrier(self, carrier: Carrier) -> Carrier:
        if hasattr(self.master_repo, "add_carrier"):
            self.master_repo.add_carrier(carrier)
        return carrier

    def get_carrier(self, carrier_id_or_code: str) -> Carrier | None:
        return self.master_repo.get_carrier_by_id(carrier_id_or_code)

    def add_vessel(self, vessel: Vessel) -> Vessel:
        if hasattr(self.master_repo, "add_vessel"):
            self.master_repo.add_vessel(vessel)
        return vessel

    def add_flight_schedule(self, schedule: FlightSchedule) -> FlightSchedule:
        if hasattr(self.master_repo, "add_flight_schedule"):
            self.master_repo.add_flight_schedule(schedule)
        return schedule

    def find_flight_schedules(self, origin_id: str, dest_id: str) -> list[FlightSchedule]:
        if hasattr(self.master_repo, "find_flight_schedules"):
            return self.master_repo.find_flight_schedules(origin_id, dest_id)
        return []

    def add_vessel_schedule(self, schedule: VesselSchedule) -> VesselSchedule:
        if hasattr(self.master_repo, "add_vessel_schedule"):
            self.master_repo.add_vessel_schedule(schedule)
        return schedule

    def find_vessel_schedules(self, origin_port: str, dest_port: str) -> list[VesselSchedule]:
        if hasattr(self.master_repo, "find_vessel_schedules"):
            return self.master_repo.find_vessel_schedules(origin_port, dest_port)
        return []

    # =========================================================================
    # Customer & Vendor Master (SRS Section 2.3)
    # =========================================================================

    def register_customer(
        self,
        name: str,
        credit_limit_amount: float,
        credit_limit_currency: str = "USD",
        payment_terms_days: int = 30,
        credit_tier: CreditTier = CreditTier.NEW,
        tax_registration: str = "",
        registration_number: str = "",
        iata_fiata_membership: str = "",
        preferred_carrier_ids: list[str] | None = None,
        preferred_lanes: list[dict] | None = None,
        contacts: list[CustomerContact] | None = None,
        addresses: list[CustomerAddress] | None = None,
        custom_code: str | None = None,
    ) -> Customer:
        """
        Creates customer record with automated customer code generation (e.g. CUST-0001).
        """
        if custom_code:
            code = custom_code
        elif hasattr(self.customer_repo, "generate_next_customer_code"):
            code = self.customer_repo.generate_next_customer_code()
        else:
            code = "CUST-0001"

        customer = Customer(
            customer_code=code,
            name=name,
            credit_limit_amount=credit_limit_amount,
            credit_limit_currency=credit_limit_currency,
            payment_terms_days=payment_terms_days,
            credit_tier=credit_tier,
            tax_registration=tax_registration,
            registration_number=registration_number,
            iata_fiata_membership=iata_fiata_membership,
            preferred_carrier_ids=preferred_carrier_ids or [],
            preferred_lanes=preferred_lanes or [],
        )

        if self.customer_repo:
            self.customer_repo.save_customer(customer)

        if contacts and hasattr(self.master_repo, "add_customer_contacts"):
            for c in contacts:
                c.customer_id = customer.id
            self.master_repo.add_customer_contacts(contacts)

        if addresses and hasattr(self.master_repo, "add_customer_addresses"):
            for a in addresses:
                a.customer_id = customer.id
            self.master_repo.add_customer_addresses(addresses)

        return customer

    def get_customer_credit_position(self, customer_id: str) -> dict[str, Any]:
        """
        Real-time credit position: limit, exposure, available, credit tier, blocked status (SRS Section 3.7).
        """
        if not self.customer_repo:
            raise ValueError("Customer repository not configured")

        customer = self.customer_repo.get_customer_by_id(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        exposure = self.customer_repo.get_customer_exposure(customer_id)
        available = round(customer.credit_limit_amount - exposure, 2)
        is_blocked = customer.credit_tier == CreditTier.BLOCKED or exposure >= customer.credit_limit_amount

        return {
            "customer_id": customer.id,
            "customer_code": customer.customer_code,
            "name": customer.name,
            "credit_limit": customer.credit_limit_amount,
            "currency": customer.credit_limit_currency,
            "total_exposure": exposure,
            "available_credit": available,
            "credit_tier": customer.credit_tier.value,
            "payment_terms_days": customer.payment_terms_days,
            "is_blocked": is_blocked,
        }

    def grant_credit_override(
        self,
        customer_id: str,
        reason: str,
        approved_by: str,
        valid_from: date,
        valid_to: date,
    ) -> CustomerCreditOverride:
        """
        Creates a Finance-approved credit override allowing bookings when credit limit is exceeded.
        """
        override = CustomerCreditOverride(
            customer_id=customer_id,
            reason=reason,
            approved_by=approved_by,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        if hasattr(self.master_repo, "save_credit_override"):
            self.master_repo.save_credit_override(override)
        return override

    def add_vendor(self, vendor: Vendor) -> Vendor:
        if hasattr(self.master_repo, "add_vendor"):
            self.master_repo.add_vendor(vendor)
        return vendor

    def add_agent(self, agent: Agent) -> Agent:
        if hasattr(self.master_repo, "add_agent"):
            self.master_repo.add_agent(agent)
        return agent

    def link_agent_rate_agreement(self, agreement: AgentRateAgreement) -> AgentRateAgreement:
        if hasattr(self.master_repo, "add_agent_rate_agreement"):
            self.master_repo.add_agent_rate_agreement(agreement)
        return agreement

    # =========================================================================
    # Reference Tables (SRS Section 2.4)
    # =========================================================================

    def add_container_type(self, container_type: ContainerType) -> ContainerType:
        self.master_repo.add_container_type(container_type)
        return container_type

    def get_container_type(self, code: str) -> ContainerType | None:
        return self.master_repo.get_container_type(code)

    def add_commodity(self, commodity: Commodity) -> Commodity:
        self.master_repo.add_commodity(commodity)
        return commodity

    def get_commodity(self, hs_code_or_id: str) -> Commodity | None:
        return self.master_repo.get_commodity_by_id(hs_code_or_id)

    def seed_standard_catalogs(self) -> None:
        """
        Pre-loads standard Incoterms, Container Types, Package Types, Charge Codes, and Currencies.
        """
        # Incoterms 2020 (all 11 codes)
        incoterms = [
            Incoterm("EXW", "Ex Works"),
            Incoterm("FCA", "Free Carrier"),
            Incoterm("CPT", "Carriage Paid To"),
            Incoterm("CIP", "Carriage and Insurance Paid To"),
            Incoterm("DAP", "Delivered at Place"),
            Incoterm("DPU", "Delivered at Place Unloaded"),
            Incoterm("DDP", "Delivered Duty Paid"),
            Incoterm("FAS", "Free Alongside Ship"),
            Incoterm("FOB", "Free on Board"),
            Incoterm("CFR", "Cost and Freight"),
            Incoterm("CIF", "Cost, Insurance and Freight"),
        ]
        if hasattr(self.master_repo, "add_incoterms"):
            self.master_repo.add_incoterms(incoterms)

        # Standard Container Types
        containers = [
            ContainerType("20GP", cbm_capacity=33.2, max_payload_kg=28200),
            ContainerType("40GP", cbm_capacity=67.7, max_payload_kg=26700),
            ContainerType("40HC", cbm_capacity=76.3, max_payload_kg=26500),
            ContainerType("20RF", cbm_capacity=28.3, max_payload_kg=27700),
            ContainerType("40RF", cbm_capacity=59.3, max_payload_kg=29500),
            ContainerType("20OT", cbm_capacity=32.5, max_payload_kg=28000),
            ContainerType("40OT", cbm_capacity=66.0, max_payload_kg=26500),
            ContainerType("20FR", cbm_capacity=27.9, max_payload_kg=31000),
            ContainerType("40FR", cbm_capacity=54.8, max_payload_kg=39000),
        ]
        for c in containers:
            self.add_container_type(c)

        # Standard Package Types (UN/CEFACT)
        pkg_types = [
            PackageType("CTN", "Carton"),
            PackageType("PLT", "Pallet"),
            PackageType("DRM", "Drum"),
            PackageType("BAG", "Bag"),
            PackageType("BDL", "Bundle"),
            PackageType("BOX", "Box"),
            PackageType("CRATE", "Crate"),
        ]
        if hasattr(self.master_repo, "add_package_types"):
            self.master_repo.add_package_types(pkg_types)

        # Standard Charge Codes
        charge_codes = [
            ChargeCode("OFT", "Ocean Freight", charge_type="FREIGHT", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("AFT", "Air Freight", charge_type="FREIGHT", rate_basis="PER_KG", applicable_mode="AIR"),
            ChargeCode("BAF", "Bunker Adjustment Factor", charge_type="SURCHARGE", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("FSC", "Fuel Surcharge", charge_type="SURCHARGE", rate_basis="PER_KG", applicable_mode="AIR"),
            ChargeCode("THC_O", "Terminal Handling Origin", charge_type="LOCAL", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("THC_D", "Terminal Handling Destination", charge_type="LOCAL", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("DOC", "Documentation Fee", charge_type="LOCAL", rate_basis="FLAT", applicable_mode="ALL"),
            ChargeCode("CUSTOMS", "Customs Clearance", charge_type="LOCAL", rate_basis="FLAT", applicable_mode="ALL"),
            ChargeCode("DGR_SUR", "Dangerous Goods Surcharge", charge_type="SURCHARGE", rate_basis="FLAT", applicable_mode="ALL"),
            ChargeCode("PSS", "Peak Season Surcharge", charge_type="SURCHARGE", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("EBS", "Emergency Bunker Surcharge", charge_type="SURCHARGE", rate_basis="PER_CONTAINER", applicable_mode="SEA"),
            ChargeCode("AWB_FEE", "Air Waybill Fee", charge_type="LOCAL", rate_basis="FLAT", applicable_mode="AIR"),
            ChargeCode("SCREENING", "Cargo Screening Fee", charge_type="LOCAL", rate_basis="PER_KG", applicable_mode="AIR"),
        ]
        if hasattr(self.master_repo, "add_charge_codes"):
            self.master_repo.add_charge_codes(charge_codes)
