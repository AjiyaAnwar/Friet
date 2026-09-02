"""
Master Data Services: lookups, currency conversion, and FX rate locking.

All persistence goes through ports.Repository - these services never
touch a database directly, so they work identically today (in-memory)
and after Team 1 ships Postgres (just pass in a different repository).
"""

from dataclasses import dataclass
from datetime import date

from ports import InMemoryRepository
from master_data.models import Location, ExchangeRate


class MasterDataLookupService:
    """
    Generic lookup helper for coded reference tables (Incoterm,
    ContainerType, ChargeCode, etc). All of these tables share the same
    shape: get by code/id, or list/filter. One service handles them all
    instead of writing 10 nearly-identical lookup classes.
    """

    def __init__(self, repo: InMemoryRepository):
        self._repo = repo

    def get_by_code(self, code: str):
        result = self._repo.get(code)
        if result is None:
            raise LookupError(f"No record found for code '{code}'")
        return result

    def get_by_id(self, entity_id: str):
        result = self._repo.get(entity_id)
        if result is None:
            raise LookupError(f"No record found for id '{entity_id}'")
        return result

    def list_all(self, **filters):
        return self._repo.list(**filters)


class LocationSearchService:
    """
    Typeahead search for the RFQ form: GET /api/v1/locations?q=karachi&type=AIRPORT
    """

    def __init__(self, location_repo: InMemoryRepository):
        self._repo = location_repo

    def search(self, query: str, location_type: str | None = None) -> list[Location]:
        query_lower = query.strip().lower()
        candidates = self._repo.list(type=location_type) if location_type else self._repo.list()

        if not query_lower:
            return [loc for loc in candidates if loc.is_active]

        return [
            loc for loc in candidates
            if loc.is_active and (
                query_lower in loc.name.lower()
                or query_lower in loc.city.lower()
                or query_lower in (loc.un_locode or "").lower()
                or query_lower in (loc.iata_code or "").lower()
            )
        ]


class CurrencyConversionError(Exception):
    pass


class CurrencyConversionService:
    """
    Converts amounts between currencies using EXCHANGE_RATE records.
    Every currency's exchange rate is stored as "rate_to_base" (i.e. how
    much of the base currency one unit of this currency is worth), so
    converting A -> B goes via the base currency: A -> base -> B.
    """

    def __init__(self, exchange_rate_repo: InMemoryRepository, base_currency: str):
        self._repo = exchange_rate_repo
        self.base_currency = base_currency

    def get_rate_to_base(self, currency_code: str, on_date: date) -> float:
        if currency_code == self.base_currency:
            return 1.0

        rates: list[ExchangeRate] = [
            r for r in self._repo.list(currency_code=currency_code)
            if r.rate_date <= on_date
        ]
        if not rates:
            raise CurrencyConversionError(
                f"No exchange rate available for {currency_code} on or before {on_date}"
            )
        latest = max(rates, key=lambda r: r.rate_date)
        return latest.rate_to_base

    def convert(self, amount: float, from_currency: str, to_currency: str, on_date: date) -> float:
        if from_currency == to_currency:
            return round(amount, 2)

        amount_in_base = amount * self.get_rate_to_base(from_currency, on_date)
        rate_to = self.get_rate_to_base(to_currency, on_date)
        return round(amount_in_base / rate_to, 2)


@dataclass
class FXLock:
    id: str
    entity_type: str
    entity_id: str
    currency_code: str
    locked_rate_to_base: float
    locked_on_date: date


class FXLockingService:
    """
    Freezes an exchange rate at a specific moment (quotation time, invoice
    time, or payment time - configurable per SRS 2.4) so downstream
    calculations don't shift if rates move later. Also computes realized/
    unrealized FX gain or loss once a later rate is known.
    """

    def __init__(self, fx_lock_repo: InMemoryRepository, conversion_service: CurrencyConversionService):
        self._repo = fx_lock_repo
        self._conversion = conversion_service

    def lock_rate(self, lock_id: str, entity_type: str, entity_id: str, currency_code: str, on_date: date) -> FXLock:
        rate = self._conversion.get_rate_to_base(currency_code, on_date)
        lock = FXLock(
            id=lock_id,
            entity_type=entity_type,
            entity_id=entity_id,
            currency_code=currency_code,
            locked_rate_to_base=rate,
            locked_on_date=on_date,
        )
        return self._repo.add(lock)

    def get_lock(self, entity_type: str, entity_id: str) -> FXLock | None:
        matches = self._repo.list(entity_type=entity_type, entity_id=entity_id)
        return matches[0] if matches else None


def calculate_fx_gain_loss(
    amount_foreign: float,
    locked_rate_to_base: float,
    settlement_rate_to_base: float,
) -> float:
    """
    Realized/unrealized FX gain or loss, in base currency terms.
    Positive = gain (currency appreciated since locking).
    Negative = loss (currency depreciated since locking).
    """
    value_at_lock = amount_foreign * locked_rate_to_base
    value_at_settlement = amount_foreign * settlement_rate_to_base
    return round(value_at_settlement - value_at_lock, 2)