"""Unit and integration test suite for Phase 4.6: ETA/ETD Multi-Version Tracking & Cascade."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.domain import EtaHistory, Shipment, ShipmentLeg
from app.db.session import get_db
from app.main import app
from app.modules.eta.alerts import evaluate_eta_deviations
from app.modules.eta.cascade import calculate_leg_cascade
from app.modules.eta.service import EtaService


# ---------------------------------------------------------------------------
# Phase 4.6 Tests: Append-Only Immutable Versioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eta_version_append_only_behavior():
    """Verify that multiple ETA updates for the same leg increment version and never overwrite."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    leg_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    leg = ShipmentLeg(
        shipment_id=shipment_id,
        origin="PKKHI",
        destination="AEJEA",
        etd=datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc),
        eta=datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc),
    )
    leg.id = leg_id

    # 1. First version (v1)
    mock_exec_leg = MagicMock()
    mock_exec_leg.scalar_one_or_none.return_value = leg

    mock_exec_ver0 = MagicMock()
    mock_exec_ver0.scalars.return_value.first.return_value = None

    mock_exec_all_legs = MagicMock()
    mock_exec_all_legs.scalars.return_value.all.return_value = [leg]

    mock_exec_all_hist = MagicMock()
    mock_exec_all_hist.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [
        mock_exec_leg,       # leg lookup
        mock_exec_ver0,      # latest version lookup -> None
        mock_exec_all_legs,  # cascade legs lookup
        mock_exec_all_hist,  # all history for alerts
    ]

    service = EtaService(mock_session)
    res_v1 = await service.record_version(
        shipment_id=shipment_id,
        leg_id=leg_id,
        type="ETA",
        value=datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc),
        source="BOOKING",
        reason="Initial planned arrival",
        recorded_by=actor_id,
        tenant_id=tenant_id,
    )

    assert res_v1["version"] == 1
    assert res_v1["type"] == "ETA"
    assert res_v1["source"] == "BOOKING"
    assert leg.eta == datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc)

    # 2. Second version (v2) on same leg
    existing_v1 = EtaHistory(
        shipment_id=shipment_id,
        leg_id=leg_id,
        type="ETA",
        version=1,
        value=datetime(2026, 9, 12, 18, 0, tzinfo=timezone.utc),
        source="BOOKING",
    )

    mock_exec_ver1 = MagicMock()
    mock_exec_ver1.scalars.return_value.first.return_value = existing_v1

    mock_session.execute.side_effect = [
        mock_exec_leg,       # leg lookup
        mock_exec_ver1,      # latest version lookup -> v1
        mock_exec_all_legs,  # cascade legs lookup
        mock_exec_all_hist,  # all history for alerts
    ]

    res_v2 = await service.record_version(
        shipment_id=shipment_id,
        leg_id=leg_id,
        type="ETA",
        value=datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc),
        source="CARRIER_API",
        reason="Vessel delayed due to port congestion",
        recorded_by=actor_id,
        tenant_id=tenant_id,
    )

    assert res_v2["version"] == 2
    assert res_v2["source"] == "CARRIER_API"
    assert leg.eta == datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    # Confirm v1 object was not overwritten
    assert existing_v1.version == 1


# ---------------------------------------------------------------------------
# Phase 4.6 Tests: Multi-Leg Cascade through 3+ Legs
# ---------------------------------------------------------------------------

def test_multi_leg_cascade_through_three_legs():
    """Verify when Leg 1 ETA is delayed, downstream Leg 2 and Leg 3 ETD/ETA auto-cascade."""
    leg1_id = "leg-1-khi-dxb"
    leg2_id = "leg-2-dxb-rot"
    leg3_id = "leg-3-rot-ham"

    legs = [
        {
            "id": leg1_id,
            "origin": "PKKHI",
            "destination": "AEDXB",
            "etd": datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
            "eta": datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        },
        {
            "id": leg2_id,
            "origin": "AEDXB",
            "destination": "NLRTM",
            "etd": datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc),  # original buffer 18h
            "eta": datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc), # 10.5 days transit
        },
        {
            "id": leg3_id,
            "origin": "NLRTM",
            "destination": "DEHAM",
            "etd": datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
            "eta": datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc), # 2 days 4h transit
        },
    ]

    # Leg 1 is delayed by 3 days: arrival shifts from Sept 4 to Sept 7 12:00
    new_leg1_eta = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

    cascade_plan = calculate_leg_cascade(
        legs=legs,
        changed_leg_id=leg1_id,
        new_eta=new_leg1_eta,
        min_connection_hours=6.0,
    )

    # We expect updates for Leg 2 (ETD & ETA) and Leg 3 (ETD & ETA) -> 4 records
    assert len(cascade_plan) == 4

    updates_by_leg = {}
    for item in cascade_plan:
        updates_by_leg.setdefault(item["leg_id"], {})[item["type"]] = item

    # Leg 2 check: earliest departure = Sept 7 12:00 + 6h = Sept 7 18:00
    assert leg2_id in updates_by_leg
    leg2_etd = updates_by_leg[leg2_id]["ETD"]["value"]
    leg2_eta = updates_by_leg[leg2_id]["ETA"]["value"]
    assert leg2_etd == datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)
    # Transit duration was 10.5 days (252h) -> ETA = Sept 18 06:00
    assert leg2_eta == datetime(2026, 9, 18, 6, 0, tzinfo=timezone.utc)
    assert updates_by_leg[leg2_id]["ETD"]["source"] == "AUTO_CASCADE"

    # Leg 3 check: earliest departure = Sept 18 06:00 + 6h = Sept 18 12:00
    assert leg3_id in updates_by_leg
    leg3_etd = updates_by_leg[leg3_id]["ETD"]["value"]
    leg3_eta = updates_by_leg[leg3_id]["ETA"]["value"]
    assert leg3_etd == datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    # Transit duration was 2 days 4h (52h) -> ETA = Sept 20 16:00
    assert leg3_eta == datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)
    assert updates_by_leg[leg3_id]["ETA"]["source"] == "AUTO_CASCADE"


# ---------------------------------------------------------------------------
# Phase 4.6 Tests: All Four Deviation Thresholds & Firm Commitment Override
# ---------------------------------------------------------------------------

def test_eta_deviation_alert_thresholds_and_firm_commitment():
    """Verify pure function alert thresholds: >1d INFO, >3d WARNING, >7d CRITICAL, and firm commitment override."""
    leg_id = "leg-alpha"
    shipment_id = "shipment-alpha"

    base_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    # 1. No delay (or earlier) -> no alerts
    records_none = [
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 1, "value": base_time},
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 2, "value": base_time},
    ]
    alerts_0 = evaluate_eta_deviations(records=records_none, has_firm_delivery_commitment=False)
    assert len(alerts_0) == 0

    # 2. Delay of 1.5 days (> 1 day) -> INFO
    records_info = [
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 1, "value": base_time},
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 2, "value": base_time + timedelta(days=1.5)},
    ]
    alerts_info = evaluate_eta_deviations(records=records_info, has_firm_delivery_commitment=False)
    assert len(alerts_info) == 1
    assert alerts_info[0]["severity"] == "INFO"
    assert "OPERATIONS" in alerts_info[0]["recipients"]
    assert alerts_info[0]["publish_customer_notification"] is False

    # 3. Delay of 4.2 days (> 3 days) -> WARNING
    records_warn = [
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 1, "value": base_time},
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 2, "value": base_time + timedelta(days=4.2)},
    ]
    alerts_warn = evaluate_eta_deviations(records=records_warn, has_firm_delivery_commitment=False)
    assert len(alerts_warn) == 1
    assert alerts_warn[0]["severity"] == "WARNING"
    assert "CUSTOMER_SERVICE" in alerts_warn[0]["recipients"]
    assert alerts_warn[0]["publish_customer_notification"] is False

    # 4. Delay of 8.0 days (> 7 days) -> CRITICAL + customer.notification outbox event
    records_crit = [
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 1, "value": base_time},
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 2, "value": base_time + timedelta(days=8.0)},
    ]
    alerts_crit = evaluate_eta_deviations(records=records_crit, has_firm_delivery_commitment=False)
    assert len(alerts_crit) == 1
    assert alerts_crit[0]["severity"] == "CRITICAL"
    assert "OPERATIONS_MANAGER" in alerts_crit[0]["recipients"]
    assert alerts_crit[0]["publish_customer_notification"] is True

    # 5. Firm Delivery Commitment override: ANY delay (e.g. 2 hours) -> immediate CRITICAL
    records_firm = [
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 1, "value": base_time},
        {"leg_id": leg_id, "shipment_id": shipment_id, "type": "ETA", "version": 2, "value": base_time + timedelta(hours=2)},
    ]
    alerts_firm = evaluate_eta_deviations(records=records_firm, has_firm_delivery_commitment=True)
    assert len(alerts_firm) == 1
    assert alerts_firm[0]["severity"] == "CRITICAL"
    assert alerts_firm[0]["firm_commitment_override"] is True
    assert alerts_firm[0]["publish_customer_notification"] is True


# ---------------------------------------------------------------------------
# Phase 4.6 Tests: API Endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eta_api_endpoints():
    """Verify FastAPI routes for recording versions and retrieving leg ETA history."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    leg_id = uuid.uuid4()

    current_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        permissions={"shipment:create", "shipment:read"},
        roles={"OPERATIONS"},
        is_portal=False,
    )

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record ETA Version via API
        post_resp = await client.post(
            f"/api/v1/shipments/{shipment_id}/eta-history",
            json={
                "leg_id": str(leg_id),
                "type": "ETA",
                "value": "2026-09-15T14:30:00Z",
                "source": "CARRIER_API",
                "reason": "Vessel ETA revised",
                "has_firm_delivery_commitment": False,
            },
        )
        assert post_resp.status_code == 200
        post_data = post_resp.json()["data"]
        assert post_data["type"] == "ETA"
        assert post_data["source"] == "CARRIER_API"

        # 2. Get Leg ETA History via API
        get_resp = await client.get(
            f"/api/v1/shipments/{shipment_id}/eta-history/{leg_id}"
        )
        assert get_resp.status_code == 200
        assert "data" in get_resp.json()

    app.dependency_overrides.clear()

