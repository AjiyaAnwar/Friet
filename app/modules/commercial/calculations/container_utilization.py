"""
Sea Freight FCL Container Utilization Calculator.

- Volume utilization = (Total CBM / Container CBM capacity) x 100%
- Weight utilization = (Gross Weight / Max payload) x 100%
- Effective utilization = MIN(volume_pct, weight_pct)
- Warnings if volume > 95% or weight > 90% (configurable per container type)
- Suggestions: e.g. if 40GP volume > 95%, suggest 40HC
"""

from dataclasses import dataclass, field


# Standard container specs: CBM capacity (m3) and max payload (kg).
# Real system would pull these from the container-types master table (Phase 2.4).
CONTAINER_SPECS = {
    "20GP": {"cbm_capacity": 33.2, "max_payload_kg": 28200},
    "40GP": {"cbm_capacity": 67.7, "max_payload_kg": 26700},
    "40HC": {"cbm_capacity": 76.3, "max_payload_kg": 26500},
    "20RF": {"cbm_capacity": 28.3, "max_payload_kg": 27700},
    "40RF": {"cbm_capacity": 59.3, "max_payload_kg": 29500},
}

UPGRADE_SUGGESTIONS = {
    "40GP": "40HC",
    "20GP": "40GP",
}

VOLUME_WARNING_THRESHOLD_PCT = 95.0
WEIGHT_WARNING_THRESHOLD_PCT = 90.0


@dataclass
class ContainerUtilizationResult:
    container_type: str
    volume_utilization_pct: float
    weight_utilization_pct: float
    effective_utilization_pct: float
    warnings: list[str] = field(default_factory=list)
    suggested_container_type: str | None = None


def calculate_container_utilization(
    total_cbm: float,
    gross_weight_kg: float,
    container_type: str,
) -> ContainerUtilizationResult:
    if container_type not in CONTAINER_SPECS:
        raise ValueError(f"Unknown container type: {container_type}")

    specs = CONTAINER_SPECS[container_type]

    volume_pct = (total_cbm / specs["cbm_capacity"]) * 100
    weight_pct = (gross_weight_kg / specs["max_payload_kg"]) * 100
    effective_pct = min(volume_pct, weight_pct)

    warnings: list[str] = []
    suggested_type = None

    if volume_pct > VOLUME_WARNING_THRESHOLD_PCT:
        warnings.append(
            f"Volume utilization {volume_pct:.1f}% exceeds "
            f"{VOLUME_WARNING_THRESHOLD_PCT}% threshold"
        )
        suggested_type = UPGRADE_SUGGESTIONS.get(container_type)

    if weight_pct > WEIGHT_WARNING_THRESHOLD_PCT:
        warnings.append(
            f"Weight utilization {weight_pct:.1f}% exceeds "
            f"{WEIGHT_WARNING_THRESHOLD_PCT}% threshold"
        )
        if suggested_type is None:
            suggested_type = UPGRADE_SUGGESTIONS.get(container_type)

    return ContainerUtilizationResult(
        container_type=container_type,
        volume_utilization_pct=round(volume_pct, 2),
        weight_utilization_pct=round(weight_pct, 2),
        effective_utilization_pct=round(effective_pct, 2),
        warnings=warnings,
        suggested_container_type=suggested_type,
    )
