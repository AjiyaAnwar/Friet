"""
In-Memory Repository Adapters for Test Harness & Autonomous Development.

Allows Team 2 to run full commercial lifecycle workflows and tests without
depending on Team 1 database or messaging infrastructure.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.entities import (
    Rfq,
    Rate,
    RateVersion,
    Route,
    Quotation,
    Customer,
    CustomerContact,
    CustomerAddress,
    CustomerCreditOverride,
    Location,
    Country,
    Zone,
    Carrier,
    Vessel,
    VesselSchedule,
    FlightSchedule,
    ContainerType,
    Commodity,
    PackageType,
    Incoterm,
    ChargeCode,
    DocumentType,
    Vendor,
    Agent,
    AgentRateAgreement,
    Job,
    MarginRule,
    ExchangeRate,
)


class InMemoryRfqRepository:
    def __init__(self) -> None:
        self._rfqs: dict[str, Rfq] = {}

    def save(self, rfq: Rfq) -> Rfq:
        self._rfqs[rfq.id] = rfq
        return rfq

    def get_by_id(self, rfq_id: str) -> Rfq | None:
        return self._rfqs.get(rfq_id)

    def list_all(
        self,
        status: str | None = None,
        assigned_to: str | None = None,
    ) -> list[Rfq]:
        results = list(self._rfqs.values())

        if status:
            results = [r for r in results if r.status.value == status]

        if assigned_to:
            results = [r for r in results if r.assigned_to == assigned_to]

        return results


class InMemoryRateRepository:
    def __init__(self) -> None:
        self._rates: dict[str, Rate] = {}

    def save_rate(self, rate: Rate) -> Rate:
        self._rates[rate.id] = rate
        return rate

    def get_rate_by_id(self, rate_id: str) -> Rate | None:
        return self._rates.get(rate_id)

    def get_rate_version_by_id(self, version_id: str) -> RateVersion | None:
        for rate in self._rates.values():
            for version in rate.versions:
                if version.id == version_id:
                    return version
        return None

    def list_all_rates(self) -> list[Rate]:
        return list(self._rates.values())

    def find_rates(
        self,
        origin_id: str,
        destination_id: str,
        effective_date: date,
        customer_id: str | None = None,
        commodity_id: str | None = None,
    ) -> list[Rate]:
        results: list[Rate] = []

        for rate in self._rates.values():
            if (
                rate.origin_location_id != origin_id
                or rate.destination_location_id != destination_id
            ):
                continue

            if not (rate.effective_date <= effective_date <= rate.expiry_date):
                continue

            if rate.status.value != "ACTIVE":
                continue

            if customer_id and rate.customer_id and rate.customer_id != customer_id:
                continue

            if commodity_id and rate.commodity_id and rate.commodity_id != commodity_id:
                continue

            results.append(rate)

        return results


class InMemoryRouteRepository:
    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}

    def save_route(self, route: Route) -> Route:
        self._routes[route.id] = route
        return route

    def find_routes(
        self,
        origin_id: str,
        destination_id: str,
        mode: str,
    ) -> list[Route]:
        return [
            r
            for r in self._routes.values()
            if r.origin_location_id == origin_id
            and r.destination_location_id == destination_id
            and r.mode.upper() == mode.upper()
        ]


class InMemoryQuotationRepository:
    def __init__(self) -> None:
        self._quotations: dict[str, Quotation] = {}

    def save_quotation(self, quotation: Quotation) -> Quotation:
        self._quotations[quotation.id] = quotation
        return quotation

    def get_by_id(self, quotation_id: str) -> Quotation | None:
        return self._quotations.get(quotation_id)

    def get_by_rfq_id(self, rfq_id: str) -> list[Quotation]:
        return [
            q for q in self._quotations.values()
            if q.rfq_id == rfq_id
        ]


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self._customers: dict[str, Customer] = {}
        self._exposures: dict[str, float] = {}
        self._customer_seq: int = 0

    def generate_next_customer_code(self) -> str:
        self._customer_seq += 1
        return f"CUST-{self._customer_seq:04d}"

    def save_customer(self, customer: Customer) -> Customer:
        self._customers[customer.id] = customer
        return customer

    def get_customer_by_id(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def set_exposure(self, customer_id: str, amount: float) -> None:
        self._exposures[customer_id] = amount

    def get_customer_exposure(self, customer_id: str) -> float:
        return self._exposures.get(customer_id, 0.0)

    def list_all_customers(self) -> list[Customer]:
        return list(self._customers.values())


class InMemoryMasterDataRepository:
    def __init__(self) -> None:
        self._countries: dict[str, Country] = {}
        self._locations: dict[str, Location] = {}
        self._zones: dict[str, Zone] = {}
        self._carriers: dict[str, Carrier] = {}
        self._vessels: dict[str, Vessel] = {}
        self._vessel_schedules: list[VesselSchedule] = []
        self._flight_schedules: list[FlightSchedule] = []
        self._container_types: dict[str, ContainerType] = {}
        self._commodities: dict[str, Commodity] = {}
        self._package_types: dict[str, PackageType] = {}
        self._incoterms: dict[str, Incoterm] = {}
        self._charge_codes: dict[str, ChargeCode] = {}
        self._document_types: dict[str, DocumentType] = {}
        self._vendors: dict[str, Vendor] = {}
        self._agents: dict[str, Agent] = {}
        self._agent_rate_agreements: list[AgentRateAgreement] = []
        self._credit_overrides: list[CustomerCreditOverride] = []
        self._customer_contacts: list[CustomerContact] = []
        self._customer_addresses: list[CustomerAddress] = []

    # Geographic
    def add_country(self, country: Country) -> None:
        self._countries[country.iso_code.upper()] = country
        self._countries[country.id] = country

    def get_country(self, iso_code: str) -> Country | None:
        return self._countries.get(iso_code.upper())

    def add_location(self, loc: Location) -> None:
        self._locations[loc.id] = loc

        if loc.un_locode:
            self._locations[loc.un_locode.upper()] = loc

        if loc.iata_code:
            self._locations[loc.iata_code.upper()] = loc

    def get_location_by_id(
        self,
        location_id_or_code: str,
    ) -> Location | None:
        return self._locations.get(
            location_id_or_code.upper(),
            self._locations.get(location_id_or_code),
        )

    def search_locations(
        self,
        query: str,
        loc_type: str | None = None,
        is_active_only: bool = True,
    ) -> list[Location]:
        q = query.lower()
        results: list[Location] = []
        seen_ids: set[str] = set()

        # A Location can be stored under multiple keys:
        # UUID, UN/LOCODE, and IATA code.
        # Deduplicate using the Location's ID.
        for loc in self._locations.values():
            if loc.id in seen_ids:
                continue

            seen_ids.add(loc.id)

            if is_active_only and not loc.is_active:
                continue

            if loc_type and loc.type != loc_type:
                continue

            if (
                q in loc.name.lower()
                or q in loc.city.lower()
                or (
                    loc.un_locode
                    and q in loc.un_locode.lower()
                )
                or (
                    loc.iata_code
                    and q in loc.iata_code.lower()
                )
            ):
                results.append(loc)

        return results

    def add_zone(self, zone: Zone) -> None:
        self._zones[zone.id] = zone
        self._zones[zone.zone_code.upper()] = zone

    def get_zone(self, code: str) -> Zone | None:
        return self._zones.get(
            code.upper(),
            self._zones.get(code),
        )

    # Carriers & Network
    def add_carrier(self, carrier: Carrier) -> None:
        self._carriers[carrier.id] = carrier

        if carrier.scac_code:
            self._carriers[carrier.scac_code.upper()] = carrier

        if carrier.iata_code:
            self._carriers[carrier.iata_code.upper()] = carrier

    def get_carrier_by_id(
        self,
        carrier_id_or_code: str,
    ) -> Carrier | None:
        return self._carriers.get(
            carrier_id_or_code.upper(),
            self._carriers.get(carrier_id_or_code),
        )

    def add_vessel(self, vessel: Vessel) -> None:
        self._vessels[vessel.id] = vessel
        self._vessels[vessel.imo_number] = vessel

    def get_vessel(self, imo_or_id: str) -> Vessel | None:
        return self._vessels.get(imo_or_id)

    def add_vessel_schedule(self, schedule: VesselSchedule) -> None:
        self._vessel_schedules.append(schedule)

    def find_vessel_schedules(
        self,
        origin_port: str,
        dest_port: str,
    ) -> list[VesselSchedule]:
        results = []

        for sched in self._vessel_schedules:
            ports = [p.get("port") for p in sched.port_rotation]

            if origin_port in ports and dest_port in ports:
                orig_idx = ports.index(origin_port)
                dest_idx = ports.index(dest_port)

                if orig_idx < dest_idx:
                    results.append(sched)

        return results

    def add_flight_schedule(self, schedule: FlightSchedule) -> None:
        self._flight_schedules.append(schedule)

    def find_flight_schedules(
        self,
        origin_id: str,
        dest_id: str,
    ) -> list[FlightSchedule]:
        return [
            f
            for f in self._flight_schedules
            if f.origin_location_id == origin_id
            and f.destination_location_id == dest_id
        ]

    # Reference
    def add_container_type(self, ct: ContainerType) -> None:
        self._container_types[ct.code.upper()] = ct

    def get_container_type(self, code: str) -> ContainerType | None:
        return self._container_types.get(code.upper())

    def add_commodity(self, com: Commodity) -> None:
        self._commodities[com.id] = com

        if com.hs_code:
            self._commodities[com.hs_code] = com

    def get_commodity_by_id(
        self,
        hs_code_or_id: str,
    ) -> Commodity | None:
        return self._commodities.get(hs_code_or_id)

    def add_package_types(self, types: list[PackageType]) -> None:
        for t in types:
            self._package_types[t.code.upper()] = t

    def add_incoterms(self, terms: list[Incoterm]) -> None:
        for t in terms:
            self._incoterms[t.code.upper()] = t

    def add_charge_codes(self, codes: list[ChargeCode]) -> None:
        for c in codes:
            self._charge_codes[c.code.upper()] = c

    # Vendor & Agent
    def add_vendor(self, vendor: Vendor) -> None:
        self._vendors[vendor.id] = vendor

        if vendor.vendor_code:
            self._vendors[vendor.vendor_code.upper()] = vendor

    def get_vendor_by_id(self, vendor_id: str) -> Vendor | None:
        return self._vendors.get(
            vendor_id.upper(),
            self._vendors.get(vendor_id),
        )

    def add_agent(self, agent: Agent) -> None:
        self._agents[agent.id] = agent

    def add_agent_rate_agreement(
        self,
        agreement: AgentRateAgreement,
    ) -> None:
        self._agent_rate_agreements.append(agreement)

    def save_credit_override(
        self,
        override: CustomerCreditOverride,
    ) -> None:
        self._credit_overrides.append(override)

    def add_customer_contacts(
        self,
        contacts: list[CustomerContact],
    ) -> None:
        self._customer_contacts.extend(contacts)

    def add_customer_addresses(
        self,
        addresses: list[CustomerAddress],
    ) -> None:
        self._customer_addresses.extend(addresses)


class InMemoryExchangeRateService:
    def __init__(self) -> None:
        # Default rates to USD base (1 unit of currency = X USD)
        self._rates_to_usd: dict[str, float] = {
            "USD": 1.0,
            "EUR": 1.08,
            "GBP": 1.28,
            "PKR": 0.0036,
            "SAR": 0.2667,
            "AED": 0.2723,
            "CNY": 0.138,
            "JPY": 0.0067,
        }

    def set_rate_to_usd(
        self,
        currency_code: str,
        rate: float,
    ) -> None:
        self._rates_to_usd[currency_code.upper()] = rate

    def get_exchange_rate(
        self,
        currency_code: str,
        effective_date: date | None = None,
    ) -> float:
        return self._rates_to_usd.get(
            currency_code.upper(),
            1.0,
        )

    def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        effective_date: date | None = None,
    ) -> float:
        if from_currency.upper() == to_currency.upper():
            return round(amount, 2)

        from_rate = self._rates_to_usd.get(
            from_currency.upper(),
            1.0,
        )

        to_rate = self._rates_to_usd.get(
            to_currency.upper(),
            1.0,
        )

        # Convert from -> USD -> to
        usd_amount = amount * from_rate
        converted = usd_amount / to_rate

        return round(converted, 2)


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []

    def publish(
        self,
        event_name: str,
        payload: dict[str, Any],
    ) -> None:
        self.published_events.append(
            {
                "event": event_name,
                "payload": payload,
            }
        )