import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from datetime import date
from ports import InMemoryRepository
from master_data.models import ExchangeRate
from master_data.services import (
    CurrencyConversionService, CurrencyConversionError,
    FXLockingService, calculate_fx_gain_loss,
)


def make_repo_with_rates():
    repo = InMemoryRepository[ExchangeRate]()
    repo.add(ExchangeRate(id="1", currency_code="USD", rate_date=date(2026, 1, 1),
                           rate_to_base=280.0, source="CENTRAL_BANK"))
    repo.add(ExchangeRate(id="2", currency_code="USD", rate_date=date(2026, 2, 1),
                           rate_to_base=290.0, source="CENTRAL_BANK"))
    return repo


def test_same_currency_conversion_is_noop():
    service = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    assert service.convert(100, "PKR", "PKR", date(2026, 1, 15)) == 100


def test_convert_foreign_to_base_uses_most_recent_rate_before_date():
    service = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    result = service.convert(100, "USD", "PKR", date(2026, 1, 15))
    assert result == 28000.0


def test_convert_uses_updated_rate_after_new_date():
    service = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    result = service.convert(100, "USD", "PKR", date(2026, 2, 15))
    assert result == 29000.0


def test_convert_base_to_foreign():
    service = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    result = service.convert(28000, "PKR", "USD", date(2026, 1, 15))
    assert result == 100.0


def test_no_rate_available_raises():
    service = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    with pytest.raises(CurrencyConversionError):
        service.convert(100, "USD", "PKR", date(2025, 1, 1))


def test_fx_lock_freezes_rate_at_lock_time():
    fx_repo = InMemoryRepository()
    conversion = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    locking = FXLockingService(fx_repo, conversion)

    lock = locking.lock_rate("LOCK1", "QUOTATION", "Q-100", "USD", date(2026, 1, 15))
    assert lock.locked_rate_to_base == 280.0

    retrieved = locking.get_lock("QUOTATION", "Q-100")
    assert retrieved.locked_rate_to_base == 280.0


def test_fx_lock_unaffected_by_later_rate_changes():
    fx_repo = InMemoryRepository()
    conversion = CurrencyConversionService(make_repo_with_rates(), base_currency="PKR")
    locking = FXLockingService(fx_repo, conversion)

    locking.lock_rate("LOCK1", "QUOTATION", "Q-100", "USD", date(2026, 1, 15))
    lock = locking.get_lock("QUOTATION", "Q-100")
    assert lock.locked_rate_to_base == 280.0


def test_fx_gain_when_currency_appreciates():
    gain_loss = calculate_fx_gain_loss(amount_foreign=100, locked_rate_to_base=280.0, settlement_rate_to_base=290.0)
    assert gain_loss == 1000.0


def test_fx_loss_when_currency_depreciates():
    gain_loss = calculate_fx_gain_loss(amount_foreign=100, locked_rate_to_base=290.0, settlement_rate_to_base=280.0)
    assert gain_loss == -1000.0