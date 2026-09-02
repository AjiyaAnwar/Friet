"""
Excel / CSV Rate Bulk Import Service (Team 2 - Phase 2).

Implements bulk rate ingestion, row-level validation, dry-run preview,
and error reporting (SRS Section 2.5).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from domain.entities import (
    Rate, RateVersion, RateLine, RateSurcharge, RateCategory, RateStatus,
    RateVersionApprovalStatus
)
from domain.interfaces import RateRepositoryPort, MasterDataRepositoryPort


@dataclass
class RowLevelImportError:
    row_number: int
    field: str
    error_message: str
    raw_value: Any = None


@dataclass
class RateImportReport:
    total_rows: int
    success_count: int
    error_count: int
    created_rate_ids: list[str] = field(default_factory=list)
    row_errors: list[RowLevelImportError] = field(default_factory=list)
    dry_run: bool = False
    is_successful: bool = True


class RateImporterService:
    def __init__(
        self,
        rate_repo: RateRepositoryPort,
        master_repo: MasterDataRepositoryPort | None = None,
    ) -> None:
        self.rate_repo = rate_repo
        self.master_repo = master_repo

    def import_rates_from_csv(
        self,
        csv_content: str,
        dry_run: bool = False,
        created_by: str = "CSV_IMPORT",
    ) -> RateImportReport:
        """
        Parses CSV string content and imports rates.
        """
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        rows = list(reader)
        return self.import_rate_rows(rows, dry_run=dry_run, created_by=created_by)

    def import_rate_rows(
        self,
        rows: list[dict[str, Any]],
        dry_run: bool = False,
        created_by: str = "BULK_IMPORT",
    ) -> RateImportReport:
        """
        Validates row-by-row and imports rates.
        """
        total_rows = len(rows)
        row_errors: list[RowLevelImportError] = []
        valid_records: list[dict[str, Any]] = []

        valid_categories = {c.value for c in RateCategory}

        for idx, row in enumerate(rows, start=1):
            errors = self._validate_row(idx, row, valid_categories)
            if errors:
                row_errors.extend(errors)
            else:
                valid_records.append(row)

        created_ids: list[str] = []

        if not row_errors and not dry_run:
            # Commit mode: group rows into Rates and RateVersions
            rates_to_save: list[Rate] = []
            for r in valid_records:
                rate_num = r.get("rate_number", f"RT-{r['carrier_code']}-{r['origin_code']}{r['dest_code']}-{idx:04d}")
                eff_date = self._parse_date(r["effective_date"])
                exp_date = self._parse_date(r["expiry_date"])
                cat = RateCategory(r["rate_category"].upper())
                amount = float(r["amount"])

                wb_from = float(r["weight_break_from"]) if r.get("weight_break_from") else None
                wb_to = float(r["weight_break_to"]) if r.get("weight_break_to") else None
                container = r.get("container_type_code")

                line = RateLine(
                    charge_code=r.get("charge_code", "OFT").upper(),
                    rate_basis=r.get("rate_basis", "PER_CONTAINER").upper(),
                    amount=amount,
                    weight_break_from=wb_from,
                    weight_break_to=wb_to,
                    container_type_code=container,
                )

                rate = Rate(
                    rate_number=rate_num,
                    rate_type=r.get("rate_type", "SEA").upper(),
                    rate_category=cat,
                    carrier_vendor_id=r["carrier_code"],
                    service_name=r.get("service_name", "Standard Service"),
                    origin_location_id=r["origin_code"],
                    destination_location_id=r["dest_code"],
                    effective_date=eff_date,
                    expiry_date=exp_date,
                    currency_code=r.get("currency", "USD").upper(),
                    customer_id=r.get("customer_id"),
                    status=RateStatus.ACTIVE,
                )

                version = RateVersion(
                    rate_id=rate.id,
                    version_number=1,
                    modified_by=created_by,
                    reason="Imported via bulk CSV",
                    lines=[line],
                )
                line.rate_version_id = version.id
                rate.versions.append(version)

                self.rate_repo.save_rate(rate)
                created_ids.append(rate.id)

        error_count = len(row_errors)
        success_count = total_rows - error_count

        return RateImportReport(
            total_rows=total_rows,
            success_count=success_count,
            error_count=error_count,
            created_rate_ids=created_ids,
            row_errors=row_errors,
            dry_run=dry_run,
            is_successful=error_count == 0,
        )

    def _validate_row(
        self,
        row_num: int,
        row: dict[str, Any],
        valid_categories: set[str],
    ) -> list[RowLevelImportError]:
        errors: list[RowLevelImportError] = []

        # Required fields check
        required = ["carrier_code", "origin_code", "dest_code", "effective_date", "expiry_date", "amount", "rate_category"]
        for field_name in required:
            val = row.get(field_name)
            if val is None or str(val).strip() == "":
                errors.append(
                    RowLevelImportError(
                        row_number=row_num,
                        field=field_name,
                        error_message=f"Missing mandatory field '{field_name}'",
                        raw_value=val,
                    )
                )

        if errors:
            return errors  # Stop if missing key fields

        # Validate Category
        cat_str = str(row["rate_category"]).strip().upper()
        if cat_str not in valid_categories:
            errors.append(
                RowLevelImportError(
                    row_number=row_num,
                    field="rate_category",
                    error_message=f"Invalid rate_category '{cat_str}'. Must be one of {valid_categories}",
                    raw_value=row["rate_category"],
                )
            )

        # Validate Dates
        eff_date = None
        exp_date = None
        try:
            eff_date = self._parse_date(row["effective_date"])
        except Exception:
            errors.append(
                RowLevelImportError(
                    row_number=row_num,
                    field="effective_date",
                    error_message="Invalid effective_date format. Expected YYYY-MM-DD",
                    raw_value=row["effective_date"],
                )
            )

        try:
            exp_date = self._parse_date(row["expiry_date"])
        except Exception:
            errors.append(
                RowLevelImportError(
                    row_number=row_num,
                    field="expiry_date",
                    error_message="Invalid expiry_date format. Expected YYYY-MM-DD",
                    raw_value=row["expiry_date"],
                )
            )

        if eff_date and exp_date and exp_date < eff_date:
            errors.append(
                RowLevelImportError(
                    row_number=row_num,
                    field="expiry_date",
                    error_message="expiry_date must be on or after effective_date",
                    raw_value=row["expiry_date"],
                )
            )

        # Validate Amount
        try:
            amt = float(row["amount"])
            if amt < 0:
                errors.append(
                    RowLevelImportError(
                        row_number=row_num,
                        field="amount",
                        error_message="Rate amount must be non-negative",
                        raw_value=row["amount"],
                    )
                )
        except ValueError:
            errors.append(
                RowLevelImportError(
                    row_number=row_num,
                    field="amount",
                    error_message="Invalid numeric amount",
                    raw_value=row["amount"],
                )
            )

        # Validate Locations if master repo configured
        if self.master_repo:
            origin_code = str(row["origin_code"]).strip()
            dest_code = str(row["dest_code"]).strip()
            if not self.master_repo.get_location_by_id(origin_code):
                errors.append(
                    RowLevelImportError(
                        row_number=row_num,
                        field="origin_code",
                        error_message=f"Origin location '{origin_code}' not found in location master",
                        raw_value=origin_code,
                    )
                )
            if not self.master_repo.get_location_by_id(dest_code):
                errors.append(
                    RowLevelImportError(
                        row_number=row_num,
                        field="dest_code",
                        error_message=f"Destination location '{dest_code}' not found in location master",
                        raw_value=dest_code,
                    )
                )

        return errors

    def _parse_date(self, date_val: Any) -> date:
        if isinstance(date_val, date):
            return date_val
        return datetime.strptime(str(date_val).strip(), "%Y-%m-%d").date()
