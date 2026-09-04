"""Auto-Escalation Evaluation Rules for Exception Management (SRS Phase 4.7).

Pure, testable time-based evaluation functions taking `now` as a parameter.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from app.modules.exceptions.taxonomy import DEFAULT_EXCEPTION_TAXONOMY


def evaluate_exception_escalations(
    *,
    exception: dict[str, Any],
    now: datetime | None = None,
    financial_threshold: float = 5000.0,
) -> list[dict[str, Any]]:
    """Evaluate 5 auto-escalation rules for an exception.

    Rules evaluated:
    1. Not acknowledged within 1h -> Escalate to TEAM_LEAD, publish 'sla.breach'
    2. Not assigned within 2h -> Escalate to DEPARTMENT_MANAGER
    3. SLA breached (resolution time exceeded) -> Escalate to OPERATIONS_MANAGER, publish 'customer.notification'
    4. CRITICAL and unresolved -> Escalate to BRANCH_HEAD
    5. Financial impact > threshold -> Notify FINANCE_CONTROLLER

    Returns:
        List of triggered escalation actions.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    opened_at = exception.get("opened_at")
    if isinstance(opened_at, str):
        opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
    if opened_at and opened_at.tzinfo is None:
        opened_at = opened_at.replace(tzinfo=timezone.utc)

    if not opened_at:
        return []

    acknowledged_at = exception.get("acknowledged_at")
    if isinstance(acknowledged_at, str):
        acknowledged_at = datetime.fromisoformat(acknowledged_at.replace("Z", "+00:00"))
    if acknowledged_at and acknowledged_at.tzinfo is None:
        acknowledged_at = acknowledged_at.replace(tzinfo=timezone.utc)

    status = str(exception.get("status", "OPEN")).upper()
    severity = str(exception.get("severity", "WARNING")).upper()
    owner_id = exception.get("owner_id")
    financial_impact = float(exception.get("financial_impact_estimated") or 0.0)
    exception_type = str(exception.get("exception_type", "")).upper()

    # Look up SLA duration from taxonomy or fallback 24h
    tax_config = DEFAULT_EXCEPTION_TAXONOMY.get(exception_type)
    resolution_sla_hours = tax_config.resolution_sla_hours if tax_config else 24.0

    elapsed = now - opened_at
    is_open = status not in {"RESOLVED", "CLOSED"}

    escalations: list[dict[str, Any]] = []

    # Rule 1: Not acknowledged within 1 hour
    if is_open and acknowledged_at is None and elapsed > timedelta(hours=1):
        escalations.append({
            "rule_id": "RULE_1_UNACKNOWLEDGED_1H",
            "escalation_target": "TEAM_LEAD",
            "reason": f"Exception not acknowledged within 1 hour (elapsed: {elapsed.total_seconds() / 3600:.1f}h)",
            "outbox_event": "sla.breach",
            "severity": "WARNING",
        })

    # Rule 2: Not assigned within 2 hours
    if is_open and (owner_id is None or not str(owner_id).strip()) and elapsed > timedelta(hours=2):
        escalations.append({
            "rule_id": "RULE_2_UNASSIGNED_2H",
            "escalation_target": "DEPARTMENT_MANAGER",
            "reason": f"Exception unassigned after 2 hours (elapsed: {elapsed.total_seconds() / 3600:.1f}h)",
            "outbox_event": None,
            "severity": "WARNING",
        })

    # Rule 3: SLA breached (elapsed > resolution_sla_hours)
    if is_open and elapsed > timedelta(hours=resolution_sla_hours):
        escalations.append({
            "rule_id": "RULE_3_SLA_BREACHED",
            "escalation_target": "OPERATIONS_MANAGER",
            "reason": f"Resolution SLA of {resolution_sla_hours}h breached (elapsed: {elapsed.total_seconds() / 3600:.1f}h)",
            "outbox_event": "customer.notification",
            "severity": "CRITICAL",
        })

    # Rule 4: CRITICAL and unresolved
    if is_open and severity == "CRITICAL":
        escalations.append({
            "rule_id": "RULE_4_CRITICAL_UNRESOLVED",
            "escalation_target": "BRANCH_HEAD",
            "reason": "Critical severity exception requires executive attention from Branch Head",
            "outbox_event": None,
            "severity": "CRITICAL",
        })

    # Rule 5: Financial impact > threshold
    if financial_impact > financial_threshold:
        escalations.append({
            "rule_id": "RULE_5_HIGH_FINANCIAL_IMPACT",
            "escalation_target": "FINANCE_CONTROLLER",
            "reason": f"Estimated financial impact (${financial_impact:,.2f}) exceeds notification threshold (${financial_threshold:,.2f})",
            "outbox_event": None,
            "severity": "WARNING" if financial_impact < 25000 else "CRITICAL",
        })

    return escalations

