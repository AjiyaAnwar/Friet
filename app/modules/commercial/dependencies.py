"""
Dependency Injection wiring - the Commercial module's composition root.
See ports.py for why everything is a Repository, not a direct DB call.
"""

import uuid
from app.modules.commercial.ports import InMemoryRepository, ImmutableRepository
from app.modules.commercial.master_data.services import (
    LocationSearchService, CurrencyConversionService, FXLockingService,
)
from app.modules.commercial.rate_engine.versioning import RateVersioningService

_country_repo = InMemoryRepository(id_attr="id")
_location_repo = InMemoryRepository(id_attr="id")
_incoterm_repo = InMemoryRepository(id_attr="code")
_container_type_repo = InMemoryRepository(id_attr="code")
_currency_repo = InMemoryRepository(id_attr="code")
_exchange_rate_repo = InMemoryRepository(id_attr="id")
_customer_repo = InMemoryRepository(id_attr="id")

_rate_repo = InMemoryRepository(id_attr="id")
_rate_version_repo = ImmutableRepository(id_attr="id")
_rate_line_repo = ImmutableRepository(id_attr="id")
_rate_surcharge_repo = ImmutableRepository(id_attr="id")
_fx_lock_repo = InMemoryRepository(id_attr="id")


def new_id() -> str:
    return str(uuid.uuid4())


def get_country_repo(): return _country_repo
def get_location_repo(): return _location_repo
def get_incoterm_repo(): return _incoterm_repo
def get_container_type_repo(): return _container_type_repo
def get_currency_repo(): return _currency_repo
def get_exchange_rate_repo(): return _exchange_rate_repo
def get_customer_repo(): return _customer_repo
def get_rate_repo(): return _rate_repo


def get_location_search_service() -> LocationSearchService:
    return LocationSearchService(_location_repo)


def get_currency_conversion_service(base_currency: str = "PKR") -> CurrencyConversionService:
    return CurrencyConversionService(_exchange_rate_repo, base_currency=base_currency)


def get_fx_locking_service() -> FXLockingService:
    return FXLockingService(_fx_lock_repo, get_currency_conversion_service())


def get_rate_versioning_service() -> RateVersioningService:
    return RateVersioningService(_rate_version_repo, _rate_line_repo, id_generator=new_id)
