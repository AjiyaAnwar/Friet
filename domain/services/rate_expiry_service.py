"""
Rate Expiry Monitoring & Notification Service (Team 2 - Phase 2).

Implements daily rate expiry monitoring, 7-day warnings, 3-day escalations,
auto-expiration transitions, and quotation rate validity checks (SRS Section 2.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from domain.entities import Rate, RateStatus, Quotation, QuotationOption
from domain.interfaces import RateRepositoryPort, EventPublisherPort


@dataclass
class RateExpiryAlert:
    rate_id: str
    rate_number: str
    carrier_id: str
    origin_id: str
    destination_id: str
    expiry_date: date
    days_until_expiry: int
    alert_level: str  # "7_DAY_WARNING", "3_DAY_ESCALATION", "EXPIRED"
    message: str


@dataclass
class RateExpiryCheckReport:
    reference_date: date
    total_active_checked: int
    warning_7_day_count: int
    escalation_3_day_count: int
    expired_count: int
    alerts: list[RateExpiryAlert] = field(default_factory=list)
    auto_expired_rate_ids: list[str] = field(default_factory=list)


class RateExpiryService:
    def __init__(
        self,
        rate_repo: Any,
        event_publisher: EventPublisherPort | None = None,
    ) -> None:
        self.rate_repo = rate_repo
        self.event_publisher = event_publisher

    def run_daily_expiry_check(self, reference_date: date | None = None) -> RateExpiryCheckReport:
        """
        Daily scheduled task checking for rates near expiry or expired (SRS Section 2.5).
        """
        if reference_date is None:
            reference_date = date.today()

        all_rates: list[Rate] = []
        if hasattr(self.rate_repo, "list_all_rates"):
            all_rates = self.rate_repo.list_all_rates()
        elif hasattr(self.rate_repo, "_rates"):
            all_rates = list(self.rate_repo._rates.values())

        active_rates = [r for r in all_rates if r.status == RateStatus.ACTIVE]

        alerts: list[RateExpiryAlert] = []
        auto_expired_ids: list[str] = []
        warn_7_count = 0
        esc_3_count = 0
        expired_count = 0

        for rate in active_rates:
            days_left = (rate.expiry_date - reference_date).days

            if days_left < 0:
                # Expired: auto-transition to EXPIRED status
                rate.status = RateStatus.EXPIRED
                self.rate_repo.save_rate(rate)
                auto_expired_ids.append(rate.id)
                expired_count += 1
                alerts.append(
                    RateExpiryAlert(
                        rate_id=rate.id,
                        rate_number=rate.rate_number,
                        carrier_id=rate.carrier_vendor_id,
                        origin_id=rate.origin_location_id,
                        destination_id=rate.destination_location_id,
                        expiry_date=rate.expiry_date,
                        days_until_expiry=days_left,
                        alert_level="EXPIRED",
                        message=f"Rate {rate.rate_number} expired on {rate.expiry_date} and was auto-transitioned to EXPIRED",
                    )
                )
            elif days_left <= 3:
                # 3-day escalation to Pricing Manager
                esc_3_count += 1
                alerts.append(
                    RateExpiryAlert(
                        rate_id=rate.id,
                        rate_number=rate.rate_number,
                        carrier_id=rate.carrier_vendor_id,
                        origin_id=rate.origin_location_id,
                        destination_id=rate.destination_location_id,
                        expiry_date=rate.expiry_date,
                        days_until_expiry=days_left,
                        alert_level="3_DAY_ESCALATION",
                        message=f"ESCALATION: Rate {rate.rate_number} expires in {days_left} days ({rate.expiry_date})",
                    )
                )
            elif days_left <= 7:
                # 7-day warning to Pricing Team
                warn_7_count += 1
                alerts.append(
                    RateExpiryAlert(
                        rate_id=rate.id,
                        rate_number=rate.rate_number,
                        carrier_id=rate.carrier_vendor_id,
                        origin_id=rate.origin_location_id,
                        destination_id=rate.destination_location_id,
                        expiry_date=rate.expiry_date,
                        days_until_expiry=days_left,
                        alert_level="7_DAY_WARNING",
                        message=f"WARNING: Rate {rate.rate_number} expires in {days_left} days ({rate.expiry_date})",
                    )
                )

        if self.event_publisher and (alerts or auto_expired_ids):
            self.event_publisher.publish(
                "rate.expiry_check_completed",
                {
                    "reference_date": reference_date.isoformat(),
                    "total_alerts": len(alerts),
                    "auto_expired_count": len(auto_expired_ids),
                },
            )

        return RateExpiryCheckReport(
            reference_date=reference_date,
            total_active_checked=len(active_rates),
            warning_7_day_count=warn_7_count,
            escalation_3_day_count=esc_3_count,
            expired_count=expired_count,
            alerts=alerts,
            auto_expired_rate_ids=auto_expired_ids,
        )

    def validate_quotation_rate_versions(
        self,
        quotation: Quotation,
        reference_date: date | None = None,
    ) -> list[str]:
        """
        Verifies whether any rate versions referenced in quotation options have expired.
        """
        if reference_date is None:
            reference_date = date.today()

        warnings: list[str] = []
        for opt in quotation.options:
            if opt.primary_rate_version_id:
                version = self.rate_repo.get_rate_version_by_id(opt.primary_rate_version_id)
                if version:
                    parent_rate = self.rate_repo.get_rate_by_id(version.rate_id)
                    if parent_rate:
                        if parent_rate.status == RateStatus.EXPIRED or parent_rate.expiry_date < reference_date:
                            warnings.append(
                                f"Option '{opt.label}' references expired rate {parent_rate.rate_number} "
                                f"(expired {parent_rate.expiry_date})"
                            )

        return warnings
