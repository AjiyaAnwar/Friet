import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db

async def override_get_db():
    """Test double override providing session=None for fast offline API schema validation."""
    yield None

@pytest.fixture(autouse=True)
def setup_test_db():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()

client = TestClient(app, raise_server_exceptions=False)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_country():
    create_response = client.post("/api/v1/admin/countries", json={
        "iso_code": "PK", "name": "Pakistan", "region": "South Asia",
        "trade_zone": "SAARC", "is_sanctioned": False, "requires_permit": False,
    })
    assert create_response.status_code == 200
    body = create_response.json()
    assert body["success"] is True
    country_id = body["data"]["id"]

    get_response = client.get(f"/api/v1/admin/countries/{country_id}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["name"] == "Pakistan"


def test_get_nonexistent_country_returns_404():
    response = client.get("/api/v1/admin/countries/does-not-exist")
    assert response.status_code == 404


def test_create_location_and_search():
    client.post("/api/v1/admin/locations", json={
        "un_locode": "PKKAR", "iata_code": "KHI", "name": "Jinnah International",
        "country_id": "PK", "city": "Karachi", "type": "AIRPORT", "timezone": "Asia/Karachi",
    })
    response = client.get("/api/v1/locations", params={"q": "karachi", "type": "AIRPORT"})
    assert response.status_code == 200
    results = response.json()["data"]
    assert len(results) == 1
    assert results[0]["city"] == "Karachi"


def test_create_rate_and_add_version():
    create_response = client.post("/api/v1/rates", json={
        "rate_number": "RT-TEST-1", "rate_type": "AIR_FREIGHT", "rate_category": "FAK",
        "carrier_vendor_id": "CAR-1", "service_name": "Standard",
        "origin_location_id": "LOC-1", "destination_location_id": "LOC-2",
        "effective_date": "2026-01-01", "expiry_date": "2026-12-31", "currency_code": "USD",
    })
    assert create_response.status_code == 200
    rate = create_response.json()["data"]
    assert rate["status"] == "DRAFT"

    version_response = client.post(f"/api/v1/rates/{rate['id']}/versions", json={
        "modified_by": "user-1",
        "reason": "initial load",
        "lines": [
            {"charge_code": "AFR", "rate_basis": "PER_KG", "weight_break_from": 0,
             "weight_break_to": 45, "amount": 8.0},
        ],
    })
    assert version_response.status_code == 200
    version = version_response.json()["data"]
    assert version["version_number"] == 1
    assert version["approval_status"] == "DRAFT"


def test_rate_version_for_nonexistent_rate_returns_404():
    response = client.post("/api/v1/rates/does-not-exist/versions", json={
        "modified_by": "user-1", "reason": "test", "lines": [],
    })
    assert response.status_code == 404


def test_calculators_still_work_after_router_wiring():
    response = client.post("/api/v1/calculations/air-chargeable-weight", json={
        "packages": [{"gross_weight_kg": 5, "length_cm": 100, "width_cm": 100, "height_cm": 100}],
    })
    assert response.status_code == 200
    assert response.json()["basis"] == "VOLUMETRIC"


def test_expiry_report_endpoint():
    response = client.get("/api/v1/rates/monitoring/expiry")
    assert response.status_code == 200
    body = response.json()["data"]
    assert "warning" in body and "escalation" in body and "newly_expired" in body


def test_rfq_and_quotation_lifecycle():
    # 1. Create RFQ
    rfq_resp = client.post("/api/v1/rfqs", json={
        "customer_id": "cust-1", "mode": "AIR", "service_type": "EXPRESS",
        "origin_location_id": "LOC-1", "destination_location_id": "LOC-2",
        "cargo_ready_date": "2026-09-10", "gross_weight_kg": 150.0,
    })
    assert rfq_resp.status_code == 200
    rfq_id = rfq_resp.json()["data"]["id"]

    # 2. Assign RFQ
    assign_resp = client.patch(f"/api/v1/rfqs/{rfq_id}/assign", json={"assigned_to": "pricing-agent-42"})
    assert assign_resp.status_code == 200
    assert assign_resp.json()["data"]["assigned_to"] == "pricing-agent-42"
    assert assign_resp.json()["data"]["status"] == "PRICING_IN_PROGRESS"

    # 3. Create Quotation
    quote_resp = client.post("/api/v1/quotations", json={
        "rfq_id": rfq_id, "total_amount": 1250.0, "expiry_date": "2026-09-30",
    })
    assert quote_resp.status_code == 200
    quote_id = quote_resp.json()["data"]["id"]

    # 4. Accept Quotation -> Confirmed Job
    accept_resp = client.post(f"/api/v1/quotations/{quote_id}/accept", json={"customer_id": "cust-1"})
    assert accept_resp.status_code == 200
    job_data = accept_resp.json()["data"]
    assert job_data["status"] == "CONFIRMED"
    assert "job_number" in job_data


def test_database_unavailable_returns_500():
    """Verify Section 7 production rule: when real DB is offline, returns clear 500 error."""
    from sqlalchemy.exc import OperationalError

    async def simulate_db_offline():
        raise OperationalError(
            "Connection refused",
            params=None,
            orig=ConnectionRefusedError("Unable to connect to PostgreSQL server at localhost:5432"),
        )
        yield

    app.dependency_overrides[get_db] = simulate_db_offline
    res = client.post("/api/v1/admin/countries", json={
        "iso_code": "US", "name": "United States", "region": "Americas", "trade_zone": "NAFTA",
    })
    assert res.status_code == 500
    assert res.json()["type"] == "https://freightcore/errors/internal-error"
    app.dependency_overrides[get_db] = override_get_db