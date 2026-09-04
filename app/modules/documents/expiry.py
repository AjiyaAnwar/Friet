"""Document Expiry Monitoring & Alert Logic (Phase 4.4)."""

from datetime import date, datetime, timezone
from typing import Any


def check_document_expiries(
    documents: list[dict[str, Any]],
    today: date | datetime | None = None,
    thresholds: tuple[int, int, int] = (30, 14, 7),
) -> list[dict[str, Any]]:
    """Pure, testable function evaluating document expiration against 30/14/7 day thresholds.

    Parameters:
        documents: List of document dicts containing at least 'id', 'doc_type', 'expiry_date'
        today: Target evaluation date (defaults to current UTC date)
        thresholds: (info_days, warning_days, critical_days) - default (30, 14, 7)

    Returns:
        List of structured expiry alert records.
    """
    if today is None:
        current_date = datetime.now(timezone.utc).date()
    elif isinstance(today, datetime):
        current_date = today.date()
    else:
        current_date = today

    t_info, t_warn, t_crit = thresholds
    alerts: list[dict[str, Any]] = []

    for doc in documents:
        raw_expiry = doc.get("expiry_date")
        if not raw_expiry:
            continue

        if isinstance(raw_expiry, str):
            try:
                expiry_dt = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00")).date()
            except ValueError:
                continue
        elif isinstance(raw_expiry, datetime):
            expiry_dt = raw_expiry.date()
        elif isinstance(raw_expiry, date):
            expiry_dt = raw_expiry
        else:
            continue

        days_remaining = (expiry_dt - current_date).days

        if days_remaining < 0:
            severity = "EXPIRED"
            message = f"Document {doc.get('doc_type')} (ID: {doc.get('id')}) expired {abs(days_remaining)} days ago on {expiry_dt}."
        elif days_remaining <= t_crit:
            severity = "CRITICAL"
            message = f"Document {doc.get('doc_type')} expires in {days_remaining} days on {expiry_dt} (Threshold: <= {t_crit}d)."
        elif days_remaining <= t_warn:
            severity = "WARNING"
            message = f"Document {doc.get('doc_type')} expires in {days_remaining} days on {expiry_dt} (Threshold: <= {t_warn}d)."
        elif days_remaining <= t_info:
            severity = "INFO"
            message = f"Document {doc.get('doc_type')} expires in {days_remaining} days on {expiry_dt} (Threshold: <= {t_info}d)."
        else:
            continue

        alerts.append({
            "document_id": str(doc.get("id")),
            "shipment_id": str(doc.get("shipment_id")) if doc.get("shipment_id") else None,
            "doc_type": doc.get("doc_type"),
            "document_name": doc.get("document_name"),
            "expiry_date": str(expiry_dt),
            "days_remaining": days_remaining,
            "severity": severity,
            "message": message,
        })

    alerts.sort(key=lambda item: item["days_remaining"])
    return alerts

