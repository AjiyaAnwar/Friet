"""Comprehensive tests for Team 2 Commercial Backend endpoints (Phases 1, 2, 3, 5, 7)."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentUser, get_current_user
from app.db.session import get_db
from app.main import app

TEST_TENANT = uuid.UUID("22222222-2222-2222-2222-222222222222")
TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

TEST_ADMIN = CurrentUser(
    id=TEST_USER_ID,
    tenant_id=TEST_TENANT,
    customer_id=None,
    permissions={
        "rate:create", "rate:read", "quotation:read", "quotation:approve", "finance:read", "audit:read"
    },
    roles={"SUPER_ADMIN", "FINANCE_CONTROLLER", "PRICING"},
    is_portal=False,
)

async def override_get_db():
    yield None

async def override_get_current_user():
    return TEST_ADMIN

@pytest.fixture(autouse=True)
def setup_test_environment():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.clear()

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 1. Reference Data Lookup Endpoints
# ---------------------------------------------------------------------------

def test_reference_lookup_endpoints():
    # Incoterm
    resp = client.get("/api/v1/admin/incoterms")
    assert resp.status_code == 200
    assert "data" in resp.json()

    # Container Types
    resp = client.get("/api/v1/admin/container-types")
    assert resp.status_code == 200

    # Commodities
    resp = client.get("/api/v1/admin/commodities")
    assert resp.status_code == 200

    # Currencies
    resp = client.get("/api/v1/admin/currencies")
    assert resp.status_code == 200

    # Package Types
    resp = client.get("/api/v1/admin/package-types")
    assert resp.status_code == 200

    # ULD Types
    resp = client.get("/api/v1/admin/uld-types")
    assert resp.status_code == 200

    # Charge Codes
    resp = client.get("/api/v1/admin/charge-codes")
    assert resp.status_code == 200

    # Document Types
    resp = client.get("/api/v1/admin/document-types")
    assert resp.status_code == 200


def test_air_schedules_search():
    resp = client.get("/api/v1/schedules/air?origin=PKKHI&destination=AEDXB")
    assert resp.status_code == 200
    assert "data" in resp.json()


# ---------------------------------------------------------------------------
# 2. Party Master & Credit Management
# ---------------------------------------------------------------------------

def test_party_master_and_credit_endpoints():
    # List customers
    resp = client.get("/api/v1/customers")
    assert resp.status_code == 200

    # List vendors
    resp = client.get("/api/v1/vendors")
    assert resp.status_code == 200

    # List agents
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 3. RFQs and Quotations Management
# ---------------------------------------------------------------------------

def test_rfq_and_quotation_listing():
    # List RFQs
    resp = client.get("/api/v1/rfqs")
    assert resp.status_code == 200
    assert "data" in resp.json()

    # List Quotations
    resp = client.get("/api/v1/quotations")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_quotation_revision_flow():
    # Create RFQ
    rfq_resp = client.post("/api/v1/rfqs", json={
        "customer_id": "cust-rev-1", "mode": "AIR", "service_type": "STANDARD",
    })
    assert rfq_resp.status_code == 200
    rfq_id = rfq_resp.json()["data"]["id"]

    # Create Initial Quotation
    quote_resp = client.post("/api/v1/quotations", json={
        "rfq_id": rfq_id, "total_amount": 1000.0, "expiry_date": "2026-10-01",
    })
    assert quote_resp.status_code == 200
    quote_id = quote_resp.json()["data"]["id"]

    # Revise Quotation
    rev_resp = client.post(f"/api/v1/quotations/{quote_id}/revise", json={
        "total_amount": 1150.0, "notes": "Price increase due to fuel surcharge",
    })
    assert rev_resp.status_code == 200
    revised_data = rev_resp.json()["data"]
    assert revised_data["parent_quotation_id"] == quote_id


# ---------------------------------------------------------------------------
# 4. Rates Listing and Side-by-Side Comparison
# ---------------------------------------------------------------------------

def test_rate_listing_and_version_compare():
    # List Rates
    resp = client.get("/api/v1/rates")
    assert resp.status_code == 200
    assert "data" in resp.json()

    # Create Rate
    r_resp = client.post("/api/v1/rates", json={
        "rate_number": "RT-CMP-1", "rate_type": "AIR_FREIGHT", "rate_category": "FAK",
        "carrier_vendor_id": "CAR-1", "service_name": "Express",
        "origin_location_id": "LOC-1", "destination_location_id": "LOC-2",
        "effective_date": "2026-01-01", "expiry_date": "2026-12-31", "currency_code": "USD",
    })
    assert r_resp.status_code == 200
    rate_id = r_resp.json()["data"]["id"]

    # Add Version 2
    v_resp = client.post(f"/api/v1/rates/{rate_id}/versions", json={
        "modified_by": "user-1", "reason": "General rate increase",
        "lines": [{"charge_code": "AFR", "rate_basis": "PER_KG", "amount": 5.5}],
    })
    assert v_resp.status_code == 200

    # Compare versions
    comp_resp = client.get(f"/api/v1/rates/{rate_id}/versions/compare?v1=1&v2=2")
    assert comp_resp.status_code == 200
    assert "version_a" in comp_resp.json()["data"]
    assert "version_b" in comp_resp.json()["data"]

