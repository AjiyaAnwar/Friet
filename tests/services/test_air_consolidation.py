import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient

from app.schemas.air_consolidation import HAWB, DeconsolidationRequest, DeconsolidationItem
from app.repositories.air_consolidation_repository import AirConsolidationRepositoryFake
from app.services.air_consolidation_service import AirConsolidationService
from app.api.v1.endpoints.air_consolidation import router, fake_repo

def test_volumetric_weight():
    repo = AirConsolidationRepositoryFake()
    service = AirConsolidationService(repo)
    # 2 cbm * 167 = 334
    assert service.calculate_volumetric_weight(Decimal("2.0")) == Decimal("334.0")

def test_get_planning_suggestions():
    repo = AirConsolidationRepositoryFake()
    
    # Add fake HAWBs
    now = datetime.now()
    repo.add_hawb(HAWB(id="H1", destination="JFK", actual_weight=Decimal("100"), volume=Decimal("1"), ready_date=now))
    repo.add_hawb(HAWB(id="H2", destination="JFK", actual_weight=Decimal("200"), volume=Decimal("1.5"), ready_date=now - timedelta(days=1)))
    repo.add_hawb(HAWB(id="H3", destination="LHR", actual_weight=Decimal("50"), volume=Decimal("0.5"), ready_date=now))
    
    service = AirConsolidationService(repo)
    
    res = service.get_planning_suggestions("JFK", Decimal("250"), Decimal("2.0"))
    
    # H2 is older, should be picked first.
    # H2 weight=200, vol=1.5. Remaining cap: 50 wt, 0.5 vol.
    # H1 weight=100, vol=1 -> won't fit because 200+100 > 250
    assert "H2" in res.suggested_hawbs
    assert "H1" not in res.suggested_hawbs
    assert res.total_actual_weight == Decimal("200")
    assert res.total_volume == Decimal("1.5")
    # vol weight = 1.5 * 167 = 250.5
    assert res.total_volumetric_weight == Decimal("250.5")
    # max(200, 250.5) = 250.5
    assert res.total_chargeable_weight == Decimal("250.5")
    
def test_deconsolidate_with_exceptions():
    repo = AirConsolidationRepositoryFake()
    service = AirConsolidationService(repo)
    
    req = DeconsolidationRequest(
        mawb_id="M1",
        location="JFK_WH",
        items=[
            DeconsolidationItem(hawb_id="H1", received_weight=Decimal("100"), condition="good"),
            DeconsolidationItem(hawb_id="H2", received_weight=Decimal("90"), condition="damaged", discrepancy_notes="water damage")
        ]
    )
    
    res = service.deconsolidate(req)
    assert res.mawb_id == "M1"
    assert res.status == "completed_with_exceptions"
    assert res.exceptions_raised == 1
    assert res.processed_items == 2
    
    # check repo
    assert "M1" in repo.deconsolidations

def test_api_planning():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    
    # Clear and set repo
    fake_repo.hawbs.clear()
    fake_repo.add_hawb(HAWB(id="H10", destination="ORD", actual_weight=Decimal("50"), volume=Decimal("0.5"), ready_date=datetime.now()))
    
    resp = client.get("/api/v1/consolidations/air/planning?target_destination=ORD&max_weight=100&max_volume=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "H10" in data["suggested_hawbs"]
    assert float(data["total_actual_weight"]) == 50.0

def test_api_deconsolidate():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    
    payload = {
        "mawb_id": "M100",
        "location": "ORD_WH",
        "items": [
            {"hawb_id": "H10", "received_weight": "50.0", "condition": "good"}
        ]
    }
    
    resp = client.post("/api/v1/consolidations/M100/deconsolidate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["exceptions_raised"] == 0
