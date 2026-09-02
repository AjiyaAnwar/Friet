"""
Rate Versioning & Immutability Service (Team 2 - Phase 2).

Implements immutable rate versioning, approval workflows, and side-by-side comparison (SRS Section 2.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from domain.entities import (
    Rate, RateVersion, RateLine, RateSurcharge, RateCategory, RateStatus,
    RateVersionApprovalStatus
)
from domain.interfaces import RateRepositoryPort


@dataclass
class RateVersionDiff:
    rate_id: str
    v1_number: int
    v2_number: int
    v1_version_id: str
    v2_version_id: str
    added_lines: list[RateLine] = field(default_factory=list)
    removed_lines: list[RateLine] = field(default_factory=list)
    modified_lines: list[dict[str, Any]] = field(default_factory=list)
    added_surcharges: list[RateSurcharge] = field(default_factory=list)
    removed_surcharges: list[RateSurcharge] = field(default_factory=list)
    modified_surcharges: list[dict[str, Any]] = field(default_factory=list)


class RateVersionService:
    def __init__(self, rate_repo: RateRepositoryPort) -> None:
        self.rate_repo = rate_repo

    def create_rate(
        self,
        rate_number: str,
        rate_type: str,
        rate_category: RateCategory,
        carrier_vendor_id: str,
        service_name: str,
        origin_location_id: str,
        destination_location_id: str,
        effective_date: date,
        expiry_date: date,
        lines: list[RateLine],
        surcharges: list[RateSurcharge] | None = None,
        currency_code: str = "USD",
        customer_id: str | None = None,
        commodity_id: str | None = None,
        created_by: str = "SYSTEM",
        reason: str = "Initial creation",
    ) -> Rate:
        """
        Creates a new Rate with immutable Version 1.
        """
        rate = Rate(
            rate_number=rate_number,
            rate_type=rate_type,
            rate_category=rate_category,
            carrier_vendor_id=carrier_vendor_id,
            service_name=service_name,
            origin_location_id=origin_location_id,
            destination_location_id=destination_location_id,
            effective_date=effective_date,
            expiry_date=expiry_date,
            currency_code=currency_code,
            customer_id=customer_id,
            commodity_id=commodity_id,
            status=RateStatus.ACTIVE,
        )

        version_1 = RateVersion(
            rate_id=rate.id,
            version_number=1,
            modified_by=created_by,
            modified_date=datetime.now(timezone.utc),
            reason=reason,
            approval_status=RateVersionApprovalStatus.APPROVED,
            lines=lines,
            surcharges=surcharges or [],
        )
        for line in lines:
            line.rate_version_id = version_1.id
        for sur in (surcharges or []):
            sur.rate_version_id = version_1.id

        rate.versions.append(version_1)
        return self.rate_repo.save_rate(rate)

    def create_new_rate_version(
        self,
        rate_id: str,
        new_lines: list[RateLine],
        new_surcharges: list[RateSurcharge] | None = None,
        modified_by: str = "PRICING_ANALYST",
        reason: str = "Rate tariff update",
        approval_status: RateVersionApprovalStatus = RateVersionApprovalStatus.APPROVED,
    ) -> RateVersion:
        """
        Every modification creates a new immutable version record (SRS Section 2.5).
        Previous versions remain completely untouched and immutable.
        Active quotations referencing previous version IDs remain valid and unchanged.
        """
        rate = self.rate_repo.get_rate_by_id(rate_id)
        if not rate:
            raise ValueError(f"Rate {rate_id} not found")

        current_max_ver = max((v.version_number for v in rate.versions), default=0)
        next_ver_num = current_max_ver + 1

        new_version = RateVersion(
            rate_id=rate.id,
            version_number=next_ver_num,
            modified_by=modified_by,
            modified_date=datetime.now(timezone.utc),
            reason=reason,
            approval_status=approval_status,
            lines=new_lines,
            surcharges=new_surcharges or [],
        )
        for line in new_lines:
            line.rate_version_id = new_version.id
        for sur in (new_surcharges or []):
            sur.rate_version_id = new_version.id

        rate.versions.append(new_version)
        self.rate_repo.save_rate(rate)
        return new_version

    def compare_rate_versions(
        self,
        rate_id: str,
        v1_number: int,
        v2_number: int,
    ) -> RateVersionDiff:
        """
        Side-by-side comparison view: version V1 vs V2 (SRS Section 2.5).
        """
        rate = self.rate_repo.get_rate_by_id(rate_id)
        if not rate:
            raise ValueError(f"Rate {rate_id} not found")

        v1 = next((v for v in rate.versions if v.version_number == v1_number), None)
        v2 = next((v for v in rate.versions if v.version_number == v2_number), None)

        if not v1 or not v2:
            raise ValueError(f"Could not find both versions {v1_number} and {v2_number} on rate {rate_id}")

        # Compare rate lines by charge code + basis + container/break
        diff = RateVersionDiff(
            rate_id=rate_id,
            v1_number=v1_number,
            v2_number=v2_number,
            v1_version_id=v1.id,
            v2_version_id=v2.id,
        )

        v1_lines_map = {
            (l.charge_code, l.rate_basis, l.container_type_code, l.weight_break_from): l
            for l in v1.lines
        }
        v2_lines_map = {
            (l.charge_code, l.rate_basis, l.container_type_code, l.weight_break_from): l
            for l in v2.lines
        }

        for key, l2 in v2_lines_map.items():
            if key not in v1_lines_map:
                diff.added_lines.append(l2)
            else:
                l1 = v1_lines_map[key]
                if l1.amount != l2.amount:
                    diff.modified_lines.append({
                        "charge_code": l2.charge_code,
                        "v1_amount": l1.amount,
                        "v2_amount": l2.amount,
                        "change": round(l2.amount - l1.amount, 2),
                    })

        for key, l1 in v1_lines_map.items():
            if key not in v2_lines_map:
                diff.removed_lines.append(l1)

        # Compare surcharges
        v1_sur_map = {s.charge_code: s for s in v1.surcharges}
        v2_sur_map = {s.charge_code: s for s in v2.surcharges}

        for code, s2 in v2_sur_map.items():
            if code not in v1_sur_map:
                diff.added_surcharges.append(s2)
            else:
                s1 = v1_sur_map[code]
                if s1.amount != s2.amount or s1.basis != s2.basis:
                    diff.modified_surcharges.append({
                        "charge_code": code,
                        "v1_amount": s1.amount,
                        "v2_amount": s2.amount,
                        "v1_basis": s1.basis,
                        "v2_basis": s2.basis,
                    })

        for code, s1 in v1_sur_map.items():
            if code not in v2_sur_map:
                diff.removed_surcharges.append(s1)

        return diff
