"""ETA/ETD Deviation Alert Engine (SRS Phase 4.6).

Pure, testable evaluation functions comparing latest ETA against original planned ETA.
"""

from datetime import datetime, timezone
from typing import Any


def evaluate_eta_deviations(
    *,
    records: list[dict[str, Any]],
    has_firm_delivery_commitment: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate ETA deviation alerts across leg history records.

    Compares latest ETA version vs the ORIGINAL planned ETA (first version recorded, version=1).

    Alert rules:
    - has_firm_delivery_commitment=True: ANY positive deviation (> 0 seconds) -> CRITICAL alert + customer.notification
    - deviation > 7 days -> CRITICAL alert + customer.notification
    - deviation > 3 days -> WARNING alert
    - deviation > 1 day -> INFO alert

    Returns:
        List of alert dictionaries.
    """
    # Group ETA records by leg_id
    leg_eta_map: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if str(r.get("type", "")).upper() != "ETA":
            continue
        leg_id = str(r.get("leg_id"))
        leg_eta_map.setdefault(leg_id, []).append(r)

    alerts: list[dict[str, Any]] = []

    for leg_id, leg_records in leg_eta_map.items():
        if not leg_records:
            continue

        # Sort by version ascending
        sorted_records = sorted(leg_records, key=lambda x: x.get("version", 1))
        original_record = sorted_records[0]
        latest_record = sorted_records[-1]

        # Extract datetime values
        original_val = original_record.get("value")
        latest_val = latest_record.get("value")

        if isinstance(original_val, str):
            original_val = datetime.fromisoformat(original_val.replace("Z", "+00:00"))
        if isinstance(latest_val, str):
            latest_val = datetime.fromisoformat(latest_val.replace("Z", "+00:00"))

        if not original_val or not latest_val:
            continue

        # Ensure timezone-aware
        if original_val.tzinfo is None:
            original_val = original_val.replace(tzinfo=timezone.utc)
        if latest_val.tzinfo is None:
            latest_val = latest_val.replace(tzinfo=timezone.utc)

        deviation_seconds = (latest_val - original_val).total_seconds()
        deviation_days = deviation_seconds / 86400.0

        if deviation_days <= 0:
            continue

        alert_severity: str | None = None
        recipient_roles: list[str] = []
        publish_customer_notification: bool = False

        if has_firm_delivery_commitment:
            # Immediate CRITICAL on any positive delay
            alert_severity = "CRITICAL"
            recipient_roles = ["OPERATIONS_MANAGER", "CUSTOMER_SERVICE", "OPERATIONS"]
            publish_customer_notification = True
        elif deviation_days > 7.0:
            alert_severity = "CRITICAL"
            recipient_roles = ["OPERATIONS_MANAGER"]
            publish_customer_notification = True
        elif deviation_days > 3.0:
            alert_severity = "WARNING"
            recipient_roles = ["OPERATIONS", "CUSTOMER_SERVICE"]
            publish_customer_notification = False
        elif deviation_days > 1.0:
            alert_severity = "INFO"
            recipient_roles = ["OPERATIONS"]
            publish_customer_notification = False

        if alert_severity:
            alerts.append({
                "leg_id": leg_id,
                "shipment_id": str(latest_record.get("shipment_id")),
                "severity": alert_severity,
                "deviation_days": round(deviation_days, 2),
                "original_eta": original_val.isoformat(),
                "latest_eta": latest_val.isoformat(),
                "original_version": original_record.get("version"),
                "latest_version": latest_record.get("version"),
                "recipients": recipient_roles,
                "publish_customer_notification": publish_customer_notification,
                "firm_commitment_override": has_firm_delivery_commitment,
                "message": (
                    f"ETA delayed by {deviation_days:.1f} days vs original plan "
                    f"({original_val.strftime('%Y-%m-%d %H:%M')} -> {latest_val.strftime('%Y-%m-%d %H:%M')})"
                ),
            })

    return alerts

