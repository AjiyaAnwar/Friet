"""
Rate Expiry Monitoring.
"""

from dataclasses import dataclass
from datetime import date

from rate_engine.models import Rate


@dataclass
class ExpiryCheckResult:
    warning: list[Rate]
    escalation: list[Rate]
    newly_expired: list[Rate]


def check_rate_expiry(
    rates: list[Rate],
    today: date,
    warning_days: int = 7,
    escalation_days: int = 3,
) -> ExpiryCheckResult:
    active_rates = [r for r in rates if r.status not in ("EXPIRED", "CANCELLED", "SUPERSEDED")]

    warning = []
    escalation = []
    newly_expired = []

    for rate in active_rates:
        days_to_expiry = (rate.expiry_date - today).days

        if days_to_expiry < 0:
            newly_expired.append(rate)
        elif days_to_expiry <= escalation_days:
            escalation.append(rate)
        elif days_to_expiry <= warning_days:
            warning.append(rate)

    return ExpiryCheckResult(warning=warning, escalation=escalation, newly_expired=newly_expired)


def apply_auto_expiry(rates: list[Rate], today: date) -> list[Rate]:
    updated = []
    for rate in rates:
        if rate.expiry_date < today and rate.status not in ("EXPIRED", "CANCELLED", "SUPERSEDED"):
            updated.append(Rate(**{**rate.__dict__, "status": "EXPIRED"}))
        else:
            updated.append(rate)
    return updated