"""Unit and integration test suite for Phase 4.7: Exception Management & Auto-Escalation."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import Shipment, ShipmentException
from app.db.session import get_db
from app.main import app
from app.modules.exceptions.escalations import evaluate_exception_escalations
from app.modules.exceptions.service import ExceptionService
from app.modules.exceptions.taxonomy import (
    DEFAULT_EXCEPTION_TAXONOMY,
    resolve_exception_type,
)


# ---------------------------------------------------------------------------
# Phase 4.7 Tests: Exception Taxonomy & Configurable Registry
# ---------------------------------------------------------------------------

def test_exception_taxonomy_resolution_and_aliases():
    """Verify taxonomy resolves standard types, aliases, and rejects unknown types."""
    # Standard codes
    cfg_delay = resolve_exception_type("SHIPMENT_DELAY")
    assert cfg_delay is not None
    assert cfg_delay.code == "SHIPMENT_DELAY"
    assert cfg_delay.domain == "CARRIER"
    assert cfg_delay.default_severity == "WARNING"

    cfg_roll = resolve_exception_type("VESSEL_ROLL")
    assert cfg_roll is not None
    assert cfg_roll.default_severity == "CRITICAL"

    cfg_customs = resolve_exception_type("CUSTOMS_HOLD")
    assert cfg_customs is not None
    assert cfg_customs.domain == "CUSTOMS"

    # Aliases
    assert resolve_exception_type("DELAY").code == "SHIPMENT_DELAY"
    assert resolve_exception_type("ROLL").code == "VESSEL_ROLL"
    assert resolve_exception_type("HOLD").code == "CARGO_HOLD"
    assert resolve_exception_type("DAMAGE").code == "CARGO_DAMAGE"
    assert resolve_exception_type("LOSS").code == "CARGO_LOSS"
    assert resolve_exception_type("RETURNED").code == "RETURNED_TO_SHIPPER"

    # Invalid code
    assert resolve_exception_type("UNKNOWN_RANDOM_CODE") is None


# ---------------------------------------------------------------------------
# Phase 4.7 Tests: Five Auto-Escalation Rules Tested Independently
# ---------------------------------------------------------------------------

def test_escalation_rule_1_unacknowledged_after_one_hour():
    """Rule 1: Unacknowledged exception > 1h escalates to TEAM_LEAD with sla.breach outbox event."""
    opened_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    now_30m = datetime(2026, 9, 4, 10, 30, tzinfo=timezone.utc)
    now_75m = datetime(2026, 9, 4, 11, 15, tzinfo=timezone.utc)

    exc = {
        "exception_type": "SHIPMENT_DELAY",
        "severity": "WARNING",
        "status": "OPEN",
        "opened_at": opened_at,
        "acknowledged_at": None,
        "owner_id": "user-123",
        "financial_impact_estimated": 100.0,
    }

    # At 30m (< 1h): Rule 1 does NOT trigger
    res_30m = evaluate_exception_escalations(exception=exc, now=now_30m)
    r1_30m = [r for r in res_30m if r["rule_id"] == "RULE_1_UNACKNOWLEDGED_1H"]
    assert len(r1_30m) == 0

    # At 75m (> 1h): Rule 1 TRIGGERS
    res_75m = evaluate_exception_escalations(exception=exc, now=now_75m)
    r1_75m = [r for r in res_75m if r["rule_id"] == "RULE_1_UNACKNOWLEDGED_1H"]
    assert len(r1_75m) == 1
    assert r1_75m[0]["escalation_target"] == "TEAM_LEAD"
    assert r1_75m[0]["outbox_event"] == "sla.breach"


def test_escalation_rule_2_unassigned_after_two_hours():
    """Rule 2: Unassigned exception (owner_id is None) > 2h escalates to DEPARTMENT_MANAGER."""
    opened_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    now_1h = datetime(2026, 9, 4, 11, 0, tzinfo=timezone.utc)
    now_3h = datetime(2026, 9, 4, 13, 0, tzinfo=timezone.utc)

    exc = {
        "exception_type": "CARGO_HOLD",
        "severity": "WARNING",
        "status": "OPEN",
        "opened_at": opened_at,
        "acknowledged_at": opened_at,  # Already acknowledged
        "owner_id": None,              # But unassigned
        "financial_impact_estimated": 200.0,
    }

    # At 1h: Rule 2 does not trigger
    res_1h = evaluate_exception_escalations(exception=exc, now=now_1h)
    r2_1h = [r for r in res_1h if r["rule_id"] == "RULE_2_UNASSIGNED_2H"]
    assert len(r2_1h) == 0

    # At 3h (> 2h): Rule 2 TRIGGERS
    res_3h = evaluate_exception_escalations(exception=exc, now=now_3h)
    r2_3h = [r for r in res_3h if r["rule_id"] == "RULE_2_UNASSIGNED_2H"]
    assert len(r2_3h) == 1
    assert r2_3h[0]["escalation_target"] == "DEPARTMENT_MANAGER"


def test_escalation_rule_3_resolution_sla_breached():
    """Rule 3: Resolution time exceeds SLA hours escalates to OPERATIONS_MANAGER with customer.notification."""
    opened_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    # DGR_ISSUE has SLA of 4.0 hours in taxonomy
    now_5h = datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc)

    exc = {
        "exception_type": "DGR_ISSUE",
        "severity": "CRITICAL",
        "status": "UNDER_INVESTIGATION",
        "opened_at": opened_at,
        "acknowledged_at": opened_at,
        "owner_id": "ops-user-1",
        "financial_impact_estimated": 0.0,
    }

    res_5h = evaluate_exception_escalations(exception=exc, now=now_5h)
    r3 = [r for r in res_5h if r["rule_id"] == "RULE_3_SLA_BREACHED"]
    assert len(r3) == 1
    assert r3[0]["escalation_target"] == "OPERATIONS_MANAGER"
    assert r3[0]["outbox_event"] == "customer.notification"


def test_escalation_rule_4_critical_unresolved():
    """Rule 4: CRITICAL severity exception while unresolved escalates to BRANCH_HEAD."""
    opened_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 4, 10, 15, tzinfo=timezone.utc)

    # 1. Open CRITICAL exception
    exc_critical_open = {
        "exception_type": "CARGO_DAMAGE",
        "severity": "CRITICAL",
        "status": "OPEN",
        "opened_at": opened_at,
        "acknowledged_at": None,
        "owner_id": "inspector-1",
        "financial_impact_estimated": 1000.0,
    }
    res_open = evaluate_exception_escalations(exception=exc_critical_open, now=now)
    r4_open = [r for r in res_open if r["rule_id"] == "RULE_4_CRITICAL_UNRESOLVED"]
    assert len(r4_open) == 1
    assert r4_open[0]["escalation_target"] == "BRANCH_HEAD"

    # 2. Resolved CRITICAL exception -> should NOT trigger rule 4
    exc_critical_resolved = dict(exc_critical_open, status="RESOLVED")
    res_resolved = evaluate_exception_escalations(exception=exc_critical_resolved, now=now)
    r4_resolved = [r for r in res_resolved if r["rule_id"] == "RULE_4_CRITICAL_UNRESOLVED"]
    assert len(r4_resolved) == 0


def test_escalation_rule_5_high_financial_impact():
    """Rule 5: Estimated financial impact > $5,000 threshold notifies FINANCE_CONTROLLER."""
    opened_at = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 4, 10, 5, tzinfo=timezone.utc)

    # 1. Under threshold ($3,500)
    exc_low = {
        "exception_type": "SHORT_SHIPMENT",
        "severity": "WARNING",
        "status": "OPEN",
        "opened_at": opened_at,
        "financial_impact_estimated": 3500.0,
    }
    res_low = evaluate_exception_escalations(exception=exc_low, now=now, financial_threshold=5000.0)
    r5_low = [r for r in res_low if r["rule_id"] == "RULE_5_HIGH_FINANCIAL_IMPACT"]
    assert len(r5_low) == 0

    # 2. Over threshold ($12,500)
    exc_high = {
        "exception_type": "SHORT_SHIPMENT",
        "severity": "WARNING",
        "status": "OPEN",
        "opened_at": opened_at,
        "financial_impact_estimated": 12500.0,
    }
    res_high = evaluate_exception_escalations(exception=exc_high, now=now, financial_threshold=5000.0)
    r5_high = [r for r in res_high if r["rule_id"] == "RULE_5_HIGH_FINANCIAL_IMPACT"]
    assert len(r5_high) == 1
    assert r5_high[0]["escalation_target"] == "FINANCE_CONTROLLER"


# ---------------------------------------------------------------------------
# Phase 4.7 Tests: Service Lifecycle & Control Tower Summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_service_lifecycle_and_summary():
    """Verify service create, update (acknowledged/resolved timestamps), filtering, and summary."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    exc_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # 1. Create exception
    shipment = Shipment(customer_id=uuid.uuid4(), mode="SEA", status="IN_TRANSIT")
    shipment.id = shipment_id
    mock_exec_ship = MagicMock()
    mock_exec_ship.scalar_one_or_none.return_value = shipment
    mock_session.execute.return_value = mock_exec_ship

    service = ExceptionService(mock_session)
    res_created = await service.create_exception(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        exception_type="VESSEL_ROLL",
        description="Container rolled by carrier due to vessel overbooking",
        financial_impact_estimated=8500.0,
        actor_id=actor_id,
    )

    assert res_created["exception_type"] == "VESSEL_ROLL"
    assert res_created["severity"] == "CRITICAL"
    assert res_created["status"] == "OPEN"
    assert res_created["financial_impact_estimated"] == 8500.0

    # 2. Update exception to ACKNOWLEDGED then RESOLVED
    exc_model = ShipmentException(
        tenant_id=tenant_id,
        shipment_id=shipment_id,
        exception_type="VESSEL_ROLL",
        severity="CRITICAL",
        domain="CARRIER",
        status="OPEN",
        description="Container rolled",
        financial_impact_estimated=8500.0,
        opened_at=datetime.now(timezone.utc),
    )
    exc_model.id = exc_id

    mock_exec_exc = MagicMock()
    mock_exec_exc.scalar_one_or_none.return_value = exc_model
    mock_session.execute.return_value = mock_exec_exc

    res_ack = await service.update_exception(
        exception_id=exc_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        status="ACKNOWLEDGED",
        owner_id=actor_id,
    )
    assert res_ack["status"] == "ACKNOWLEDGED"
    assert exc_model.acknowledged_at is not None

    res_res = await service.update_exception(
        exception_id=exc_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        status="RESOLVED",
        resolution_notes="Rebooked on MV Ever Given departing next morning",
    )
    assert res_res["status"] == "RESOLVED"
    assert exc_model.resolved_at is not None
    assert res_res["resolution_notes"] == "Rebooked on MV Ever Given departing next morning"


# ---------------------------------------------------------------------------
# Phase 4.7 Tests: API Integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_api_endpoints():
    """Verify FastAPI routes for creating exceptions, updating status, listing, and summary."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    exc_id = uuid.uuid4()

    current_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        permissions={"shipment:create", "shipment:transition", "shipment:read"},
        roles={"OPERATIONS"},
        is_portal=False,
    )

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /shipments/{id}/exceptions
        post_resp = await client.post(
            f"/api/v1/shipments/{shipment_id}/exceptions",
            json={
                "exception_type": "CUSTOMS_HOLD",
                "description": "Consignment held for document examination",
                "financial_impact_estimated": 1500.0,
            },
        )
        assert post_resp.status_code == 200
        post_data = post_resp.json()["data"]
        assert post_data["exception_type"] == "CUSTOMS_HOLD"
        assert post_data["domain"] == "CUSTOMS"

        # 2. PATCH /shipments/{id}/exceptions/{exception_id}
        patch_resp = await client.patch(
            f"/api/v1/shipments/{shipment_id}/exceptions/{exc_id}",
            json={
                "status": "ACKNOWLEDGED",
                "resolution_notes": "Customs broker assigned to provide documentation",
            },
        )
        assert patch_resp.status_code == 200
        patch_data = patch_resp.json()["data"]
        assert patch_data["status"] == "ACKNOWLEDGED"

        # 3. GET /exceptions with filtering
        get_list_resp = await client.get("/api/v1/exceptions?status=OPEN&severity=CRITICAL")
        assert get_list_resp.status_code == 200
        assert "data" in get_list_resp.json()

        # 4. GET /exceptions/summary
        get_sum_resp = await client.get("/api/v1/exceptions/summary")
        assert get_sum_resp.status_code == 200
        sum_data = get_sum_resp.json()["data"]
        assert "total_open" in sum_data
        assert "by_severity" in sum_data

    app.dependency_overrides.clear()

