"""
Foreign Exchange (FX) & Rate Locking Service (Team 2 - Phase 2).

Implements multi-currency conversion, FX rate freezing at quotation time,
and realized/unrealized FX variance calculations (SRS Section 2.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
import uuid


@dataclass
class LockedExchangeRate:
    quotation_id: str
    from_currency: str
    to_currency: str
    locked_rate: float
    locked_date: date
    stage: str = "QUOTATION"  # "QUOTATION", "INVOICE", "PAYMENT"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class FxVarianceResult:
    original_amount: float
    from_currency: str
    to_currency: str
    locked_rate: float
    current_rate: float
    locked_value: float
    current_value: float
    variance_amount: float
    is_gain: bool


class FxService:
    def __init__(self) -> None:
        # Currency rates relative to 1 USD base
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
        self._locked_rates: dict[tuple[str, str, str], LockedExchangeRate] = {}

    def set_rate_to_usd(self, currency_code: str, rate: float) -> None:
        self._rates_to_usd[currency_code.upper()] = rate

    def get_exchange_rate(self, currency_code: str, effective_date: date | None = None) -> float:
        return self._rates_to_usd.get(currency_code.upper(), 1.0)

    def convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
        effective_date: date | None = None,
        quotation_id: str | None = None,
    ) -> float:
        """
        Converts an amount from one currency to another.
        If a locked rate exists for the quotation, uses the frozen locked rate.
        """
        from_curr = from_currency.upper()
        to_curr = to_currency.upper()

        if from_curr == to_curr:
            return round(amount, 2)

        # Check if rate is locked for this quotation
        if quotation_id:
            locked = self.get_locked_rate(quotation_id, from_curr, to_curr)
            if locked:
                return round(amount * locked.locked_rate, 2)

        from_rate = self._rates_to_usd.get(from_curr, 1.0)
        to_rate = self._rates_to_usd.get(to_curr, 1.0)

        # from -> USD -> to
        usd_amount = amount * from_rate
        converted = usd_amount / to_rate
        return round(converted, 2)

    def lock_exchange_rate(
        self,
        quotation_id: str,
        from_currency: str,
        to_currency: str,
        effective_date: date,
        stage: str = "QUOTATION",
    ) -> LockedExchangeRate:
        """
        Freezes the exchange rate at quotation time so currency fluctuations
        do not impact active quotations (SRS Section 2.4).
        """
        from_curr = from_currency.upper()
        to_curr = to_currency.upper()

        if from_curr == to_curr:
            rate = 1.0
        else:
            from_rate = self._rates_to_usd.get(from_curr, 1.0)
            to_rate = self._rates_to_usd.get(to_curr, 1.0)
            rate = from_rate / to_rate

        locked = LockedExchangeRate(
            quotation_id=quotation_id,
            from_currency=from_curr,
            to_currency=to_curr,
            locked_rate=round(rate, 6),
            locked_date=effective_date,
            stage=stage,
        )
        self._locked_rates[(quotation_id, from_curr, to_curr)] = locked
        return locked

    def get_locked_rate(
        self,
        quotation_id: str,
        from_currency: str,
        to_currency: str,
    ) -> LockedExchangeRate | None:
        return self._locked_rates.get((quotation_id, from_currency.upper(), to_currency.upper()))

    def calculate_fx_variance(
        self,
        original_amount: float,
        from_currency: str,
        to_currency: str,
        quotation_id: str,
    ) -> FxVarianceResult:
        """
        Computes realized/unrealized FX variance between locked quotation rate and current rate.
        """
        from_curr = from_currency.upper()
        to_curr = to_currency.upper()

        locked = self.get_locked_rate(quotation_id, from_curr, to_curr)
        if not locked:
            raise ValueError(f"No locked FX rate found for quotation {quotation_id} ({from_curr}->{to_curr})")

        from_rate = self._rates_to_usd.get(from_curr, 1.0)
        to_rate = self._rates_to_usd.get(to_curr, 1.0)
        current_rate = from_rate / to_rate

        locked_val = round(original_amount * locked.locked_rate, 2)
        current_val = round(original_amount * current_rate, 2)
        variance = round(current_val - locked_val, 2)

        return FxVarianceResult(
            original_amount=original_amount,
            from_currency=from_curr,
            to_currency=to_curr,
            locked_rate=locked.locked_rate,
            current_rate=round(current_rate, 6),
            locked_value=locked_val,
            current_value=current_val,
            variance_amount=abs(variance),
            is_gain=variance >= 0,
        )
