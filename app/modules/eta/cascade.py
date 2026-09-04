"""Multi-leg ETA/ETD Cascade Engine (SRS Phase 4.6).

Propagates ETA delays downstream through all remaining legs in the shipment chain.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def calculate_leg_cascade(
    *,
    legs: list[dict[str, Any]],
    changed_leg_id: str,
    new_eta: datetime,
    min_connection_hours: float = 6.0,
) -> list[dict[str, Any]]:
    """Compute cascade updates for downstream legs when a leg's ETA changes.

    Args:
        legs: Ordered list of leg dictionaries for the shipment.
              Each leg dict: {
                  "id": str,
                  "origin": str,
                  "destination": str,
                  "etd": datetime,
                  "eta": datetime,
                  ...
              }
        changed_leg_id: The ID of the leg whose ETA was modified.
        new_eta: The new ETA datetime for the changed leg.
        min_connection_hours: Minimum buffer required at the transshipment point (default 6.0 hrs).

    Returns:
        List of new version records to create for downstream legs:
        [
            {
                "leg_id": str,
                "type": "ETD" | "ETA",
                "value": datetime,
                "source": "AUTO_CASCADE",
                "reason": str,
            },
            ...
        ]
    """
    if not legs:
        return []

    # Find the index of the changed leg
    changed_idx = -1
    for idx, leg in enumerate(legs):
        if str(leg.get("id")) == str(changed_leg_id):
            changed_idx = idx
            break

    if changed_idx == -1 or changed_idx >= len(legs) - 1:
        # Changed leg not found or is the final leg (no downstream legs to cascade)
        return []

    current_arrival = new_eta
    if current_arrival.tzinfo is None:
        current_arrival = current_arrival.replace(tzinfo=timezone.utc)

    cascade_records: list[dict[str, Any]] = []

    # Cascade through all remaining legs downstream
    for idx in range(changed_idx + 1, len(legs)):
        downstream_leg = legs[idx]
        leg_id = str(downstream_leg.get("id"))

        curr_etd = downstream_leg.get("etd")
        curr_eta = downstream_leg.get("eta")

        if isinstance(curr_etd, str):
            curr_etd = datetime.fromisoformat(curr_etd.replace("Z", "+00:00"))
        if isinstance(curr_eta, str):
            curr_eta = datetime.fromisoformat(curr_eta.replace("Z", "+00:00"))

        if curr_etd and curr_etd.tzinfo is None:
            curr_etd = curr_etd.replace(tzinfo=timezone.utc)
        if curr_eta and curr_eta.tzinfo is None:
            curr_eta = curr_eta.replace(tzinfo=timezone.utc)

        # Calculate original transit duration if available, else default 24h
        transit_duration = (curr_eta - curr_etd) if (curr_eta and curr_etd and curr_eta > curr_etd) else timedelta(hours=24)

        # Minimum departure time from transshipment point
        earliest_possible_departure = current_arrival + timedelta(hours=min_connection_hours)

        # If current ETD is earlier than earliest possible departure, we must delay it
        if curr_etd is None or curr_etd < earliest_possible_departure:
            new_leg_etd = earliest_possible_departure
        else:
            # Shift ETD by the delay if needed or preserve existing
            new_leg_etd = curr_etd

        new_leg_eta = new_leg_etd + transit_duration

        trigger_source_desc = f"Leg {changed_leg_id[:8]}" if len(changed_leg_id) >= 8 else f"Leg {changed_leg_id}"

        cascade_records.append({
            "leg_id": leg_id,
            "type": "ETD",
            "value": new_leg_etd,
            "source": "AUTO_CASCADE",
            "reason": f"Auto-cascaded from upstream ETA change on {trigger_source_desc}",
        })

        cascade_records.append({
            "leg_id": leg_id,
            "type": "ETA",
            "value": new_leg_eta,
            "source": "AUTO_CASCADE",
            "reason": f"Auto-cascaded from upstream ETA change on {trigger_source_desc}",
        })

        # The new arrival time at the next transshipment point is this leg's new ETA
        current_arrival = new_leg_eta

    return cascade_records

