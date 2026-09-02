"""
In-Memory Repository Adapters for Test Harness & Autonomous Development.

Allows Team 2 to run full commercial lifecycle workflows and tests without
depending on Team 1 database or messaging infrastructure.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from domain.entities import (
    Rfq, Rate, RateVersion, Route, Quotation, Customer, Location,
    Carrier, ContainerType, Commodity, Job, MarginRule, ExchangeRate
)


class InMemoryRfqRepository:
    def __init__(self) -> None:
        self._rfqs: dict[str, Rfq] = {}

    def save(self, rfq: Rfq) -> Rfq:
        self._rfqs[rfq.id] = rfq
        return rfq

    def get_by_id(self, rfq_id: str) -> Rfq | None:
        return self._rfqs.get(rfq_id)

    def list_all(self, status: str | None = None, assigned_to: str | None = None) -> list[Rfq]:
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
            if rate.origin_location_id != origin_id or rate.destination_location_id != destination_id:
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

    def find_routes(self, origin_id: str, destination_id: str, mode: str) -> list[Route]:
        return [
            r for r in self._routes.values()
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
        return [q for q in self._quotations.values() if q.rfq_id == rfq_id]


class InMemoryCustomerRepository:
    def __init__(self) -> None:
        self._customers: dict[str, Customer] = {}
        self._exposures: dict[str, float] = {}

    def save_customer(self, customer: Customer) -> Customer:
        self._customers[customer.id] = customer
        return customer

    def get_customer_by_id(self, customer_id: str) -> Customer | None:
        return self._customers.get(customer_id)

    def set_exposure(self, customer_id: str, amount: float) -> None:
        self._exposures[customer_id] = amount

    def get_customer_exposure(self, customer_id: str) -> float:
        return self._exposures.get(customer_id, 0.0)


class InMemoryMasterDataRepository:
    def __init__(self) -> None:
        self._locations: dict[str, Location] = {}
        self._carriers: dict[str, Carrier] = {}
        self._container_types: dict[str, ContainerType] = {}
        self._commodities: dict[str, Commodity] = {}

    def add_location(self, loc: Location) -> None:
        self._locations[loc.id] = loc
        if loc.un_locode:
            self._locations[loc.un_locode] = loc

    def get_location_by_id(self, location_id: str) -> Location | None:
        return self._locations.get(location_id)

    def add_carrier(self, carrier: Carrier) -> None:
        self._carriers[carrier.id] = carrier
        if carrier.scac_code:
            self._carriers[carrier.scac_code] = carrier
        if carrier.iata_code:
            self._carriers[carrier.iata_code] = carrier

    def get_carrier_by_id(self, carrier_id: str) -> Carrier | None:
        return self._carriers.get(carrier_id)

    def add_container_type(self, ct: ContainerType) -> None:
        self._container_types[ct.code] = ct

    def get_container_type(self, code: str) -> ContainerType | None:
        return self._container_types.get(code)

    def add_commodity(self, com: Commodity) -> None:
        self._commodities[com.id] = com
        if com.hs_code:
            self._commodities[com.hs_code] = com

    def get_commodity_by_id(self, commodity_id: str) -> Commodity | None:
        return self._commodities.get(commodity_id)


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
        }

    def set_rate_to_usd(self, currency_code: str, rate: float) -> None:
        self._rates_to_usd[currency_code] = rate

    def get_exchange_rate(self, currency_code: str, effective_date: date) -> float:
        return self._rates_to_usd.get(currency_code, 1.0)

    def convert(self, amount: float, from_currency: str, to_currency: str, effective_date: date | None = None) -> float:
        if from_currency == to_currency:
            return round(amount, 2)
        from_rate = self._rates_to_usd.get(from_currency, 1.0)
        to_rate = self._rates_to_usd.get(to_currency, 1.0)
        # Convert from -> USD -> to
        usd_amount = amount * from_rate
        converted = usd_amount / to_rate
        return round(converted, 2)


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        self.published_events.append({"event": event_name, "payload": payload})
