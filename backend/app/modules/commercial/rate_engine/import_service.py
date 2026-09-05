"""
Rate Import Service - Excel/CSV bulk rate upload with validation.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


REQUIRED_FIELDS = [
    "rate_number", "rate_type", "rate_category", "carrier_vendor_id",
    "origin_location_id", "destination_location_id", "effective_date",
    "expiry_date", "currency_code",
]


@dataclass
class RowError:
    row_number: int
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    total_rows: int
    success_count: int
    error_count: int
    row_errors: list[RowError] = field(default_factory=list)
    valid_rows: list[dict] = field(default_factory=list)
    dry_run: bool = True


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def validate_rate_rows(
    rows: list[dict],
    known_location_ids: set[str],
    known_carrier_ids: set[str],
    dry_run: bool = True,
) -> ImportReport:
    row_errors: list[RowError] = []
    valid_rows: list[dict] = []
    seen_rate_numbers: set[str] = set()

    for i, row in enumerate(rows, start=1):
        errors: list[str] = []

        for field_name in REQUIRED_FIELDS:
            if not row.get(field_name):
                errors.append(f"Missing required field: {field_name}")

        effective = _parse_date(row.get("effective_date"))
        expiry = _parse_date(row.get("expiry_date"))

        if row.get("effective_date") and effective is None:
            errors.append("Invalid effective_date format (expected YYYY-MM-DD)")
        if row.get("expiry_date") and expiry is None:
            errors.append("Invalid expiry_date format (expected YYYY-MM-DD)")
        if effective and expiry and effective > expiry:
            errors.append("effective_date must be on or before expiry_date")

        origin = row.get("origin_location_id")
        if origin and origin not in known_location_ids:
            errors.append(f"Unknown origin_location_id: {origin}")

        destination = row.get("destination_location_id")
        if destination and destination not in known_location_ids:
            errors.append(f"Unknown destination_location_id: {destination}")

        carrier = row.get("carrier_vendor_id")
        if carrier and carrier not in known_carrier_ids:
            errors.append(f"Unknown carrier_vendor_id: {carrier}")

        rate_number = row.get("rate_number")
        if rate_number and rate_number in seen_rate_numbers:
            errors.append(f"Duplicate rate_number within this import: {rate_number}")
        elif rate_number:
            seen_rate_numbers.add(rate_number)

        if errors:
            row_errors.append(RowError(row_number=i, errors=errors))
        else:
            valid_rows.append(row)

    return ImportReport(
        total_rows=len(rows),
        success_count=len(valid_rows),
        error_count=len(row_errors),
        row_errors=row_errors,
        valid_rows=valid_rows,
        dry_run=dry_run,
    )


def read_rate_file(file_path: str) -> list[dict]:
    import pandas as pd

    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    df = df.where(df.notnull(), None)
    return df.to_dict(orient="records")
