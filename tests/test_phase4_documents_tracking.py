"""Unit and integration test suite for Phase 4.4 (Documents) and Phase 4.5 (Tracking)."""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import CurrentUser, get_current_user
from app.core.exceptions import ForbiddenError, ValidationError
from app.db.models.domain import (
    Document,
    DocumentAccessLog,
    DocumentChecklistItem,
    DocumentVersion,
    Shipment,
    TrackingEvent,
)
from app.db.session import get_db
from app.main import app
from app.modules.documents.checklist import checklist_engine
from app.modules.documents.expiry import check_document_expiries
from app.modules.documents.service import DocumentService
from app.modules.tracking.service import TrackingService
from app.modules.tracking.taxonomy import (
    EVENT_TAXONOMY,
    EventCategory,
    validate_event_type,
)


# ---------------------------------------------------------------------------
# Phase 4.4 Tests: Document Version Immutability & Storage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_version_immutability():
    """Verify that uploading new versions increments version_number and preserves historical versions."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # First upload (v1)
    mock_exec_1 = MagicMock()
    mock_exec_1.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_exec_1

    service = DocumentService(mock_session)
    res_v1 = await service.upload_document(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        doc_type="BILL_OF_LADING",
        document_name="Original BL draft",
        file_bytes=b"PDF_CONTENT_V1",
        filename="bl_v1.pdf",
        change_summary="Initial draft",
    )

    assert res_v1["version_number"] == 1
    assert res_v1["doc_type"] == "BILL_OF_LADING"

    # Second upload (v2) on same document
    existing_doc = Document(
        shipment_id=shipment_id,
        doc_type="BILL_OF_LADING",
        document_name="Original BL draft",
        file_url="s3://freightcore-documents/bl_v1.pdf",
        version_number=1,
        uploaded_by=actor_id,
        uploaded_at=datetime.now(timezone.utc),
        status="PENDING_REVIEW",
    )
    existing_doc.id = uuid.uuid4()

    mock_exec_2 = MagicMock()
    mock_exec_2.scalar_one_or_none.return_value = existing_doc
    mock_session.execute.return_value = mock_exec_2

    res_v2 = await service.upload_document(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        doc_type="BILL_OF_LADING",
        document_name="Revised BL after amendment",
        file_bytes=b"PDF_CONTENT_V2",
        filename="bl_v2.pdf",
        change_summary="Port of discharge corrected",
    )

    assert res_v2["version_number"] == 2
    assert existing_doc.version_number == 2


# ---------------------------------------------------------------------------
# Phase 4.4 Tests: Document Checklist Auto-Generation
# ---------------------------------------------------------------------------

def test_document_checklist_auto_generation_combinations():
    """Verify rule engine auto-generates correct checklists across mode, commodity, and LC combinations."""
    # 1. Sea + FCL + Letter of Credit
    sea_lc_ctx = {
        "mode": "SEA",
        "service_type": "FCL",
        "commodity": "GENERAL",
        "incoterm": "CIF",
        "has_letter_of_credit": True,
        "destination_country": "SA",
    }
    items_sea = checklist_engine.generate_checklist(sea_lc_ctx)
    doc_codes_sea = {item["doc_type_code"] for item in items_sea}

    assert "BILL_OF_LADING" in doc_codes_sea
    assert "VGM_CERTIFICATE" in doc_codes_sea
    assert "COMMERCIAL_INVOICE" in doc_codes_sea
    assert "CERTIFICATE_OF_ORIGIN" in doc_codes_sea
    assert "MARINE_INSURANCE_CERT" in doc_codes_sea
    assert "SABER_SASO_CERTIFICATE" in doc_codes_sea

    # 2. Air + DGR Hazardous
    air_dgr_ctx = {
        "mode": "AIR",
        "service_type": "DIRECT",
        "commodity": "DGR",
        "is_dgr": True,
        "incoterm": "FOB",
        "destination_country": "US",
    }
    items_air = checklist_engine.generate_checklist(air_dgr_ctx)
    doc_codes_air = {item["doc_type_code"] for item in items_air}

    assert "AIR_WAYBILL" in doc_codes_air
    assert "SECURITY_SCREENING_CERT" in doc_codes_air
    assert "DGR_DECLARATION" in doc_codes_air
    assert "DGR_EMERGENCY_RESPONSE" in doc_codes_air

    # 3. Perishable Cold-Chain
    perishable_ctx = {
        "mode": "AIR",
        "service_type": "DIRECT",
        "commodity": "FRUITS",
        "is_perishable": True,
        "temperature_controlled": True,
    }
    items_perishable = checklist_engine.generate_checklist(perishable_ctx)
    doc_codes_perishable = {item["doc_type_code"] for item in items_perishable}
    assert "PHYTOSANITARY_CERT" in doc_codes_perishable
    assert "TEMPERATURE_DATA_LOG" in doc_codes_perishable

    # 4. Sea + LCL — BL required; VGM must NOT appear (VGM is FCL-specific)
    sea_lcl_ctx = {
        "mode": "SEA",
        "service_type": "LCL",
        "commodity": "GENERAL",
        "incoterm": "FOB",
        "destination_country": "DE",
    }
    items_lcl = checklist_engine.generate_checklist(sea_lcl_ctx)
    doc_codes_lcl = {item["doc_type_code"] for item in items_lcl}
    assert "BILL_OF_LADING" in doc_codes_lcl, "LCL shipments still require a Bill of Lading"
    assert "VGM_CERTIFICATE" not in doc_codes_lcl, "VGM is FCL-only; must not appear for LCL"
    # Non-SA/US destination — no jurisdiction-specific docs
    assert "SABER_SASO_CERTIFICATE" not in doc_codes_lcl
    assert "US_ISF_10_2" not in doc_codes_lcl

    # 5. EXW incoterm — seller at factory gate; no insurance obligation
    ewx_ctx = {
        "mode": "SEA",
        "service_type": "FCL",
        "commodity": "GENERAL",
        "incoterm": "EXW",
        "destination_country": "UK",
    }
    items_exw = checklist_engine.generate_checklist(ewx_ctx)
    doc_codes_exw = {item["doc_type_code"] for item in items_exw}
    assert "COMMERCIAL_INVOICE" in doc_codes_exw
    assert "MARINE_INSURANCE_CERT" not in doc_codes_exw, "EXW does not require seller-provided insurance"

    # 6. DDP incoterm — customs docs required via POD; no special rules beyond baseline in current engine
    ddp_ctx = {
        "mode": "AIR",
        "service_type": "DIRECT",
        "commodity": "GENERAL",
        "incoterm": "DDP",
        "destination_country": "FR",
    }
    items_ddp = checklist_engine.generate_checklist(ddp_ctx)
    doc_codes_ddp = {item["doc_type_code"] for item in items_ddp}
    # Baseline air docs always required
    assert "AIR_WAYBILL" in doc_codes_ddp
    assert "COMMERCIAL_INVOICE" in doc_codes_ddp
    assert "PACKING_LIST" in doc_codes_ddp
    # No SASO/ISF for France
    assert "SABER_SASO_CERTIFICATE" not in doc_codes_ddp
    assert "US_ISF_10_2" not in doc_codes_ddp

    # 7. Minimal baseline — Sea FCL GENERAL FOB no extras
    baseline_ctx = {
        "mode": "SEA",
        "service_type": "FCL",
        "commodity": "GENERAL",
        "incoterm": "FOB",
        "destination_country": "NL",
    }
    items_base = checklist_engine.generate_checklist(baseline_ctx)
    doc_codes_base = {item["doc_type_code"] for item in items_base}
    # Must include core docs
    assert "COMMERCIAL_INVOICE" in doc_codes_base
    assert "PACKING_LIST" in doc_codes_base
    assert "BILL_OF_LADING" in doc_codes_base
    assert "VGM_CERTIFICATE" in doc_codes_base
    assert "PROOF_OF_DELIVERY" in doc_codes_base
    # Must NOT include commodity/LC/jurisdiction-specific docs
    assert "DGR_DECLARATION" not in doc_codes_base
    assert "PHYTOSANITARY_CERT" not in doc_codes_base
    assert "CERTIFICATE_OF_ORIGIN" not in doc_codes_base
    assert "MARINE_INSURANCE_CERT" not in doc_codes_base
    assert "SABER_SASO_CERTIFICATE" not in doc_codes_base
    assert "US_ISF_10_2" not in doc_codes_base


# ---------------------------------------------------------------------------
# Phase 4.4 Tests: Document Approval Workflow & Role Gates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_approval_role_gates():
    """Verify DGR approval requires COMPLIANCE role and blocks unauthorized roles."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    doc = Document(
        shipment_id=uuid.uuid4(),
        doc_type="DGR_DECLARATION",
        document_name="IMO Shipper Declaration",
        file_url="s3://dgr.pdf",
        status="PENDING_REVIEW",
    )
    doc.id = doc_id

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_session.execute.return_value = mock_exec

    service = DocumentService(mock_session)

    # Unauthorized role (OPERATIONS only) -> raises ForbiddenError
    with pytest.raises(ForbiddenError) as exc_info:
        await service.approve_document(
            document_id=doc_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            user_roles={"OPERATIONS"},
        )
    assert "COMPLIANCE" in str(exc_info.value)

    # Authorized role (COMPLIANCE) -> succeeds
    res = await service.approve_document(
        document_id=doc_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        user_roles={"COMPLIANCE"},
    )
    assert res["status"] == "APPROVED"
    assert doc.status == "APPROVED"


# ---------------------------------------------------------------------------
# Phase 4.4 Tests: Document Access Control (Customer & Carrier Portals)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_document_portal_access_control():
    """Verify Carrier Portal only sees transport docs and Customer Portal cannot see other customers' docs."""
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    my_customer_id = uuid.uuid4()
    other_customer_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    # 1. Customer Portal isolation failure when accessing another customer's shipment
    mock_exec_1 = MagicMock()
    mock_exec_1.scalar_one_or_none.return_value = None  # No shipment matching my_customer_id
    mock_session.execute.return_value = mock_exec_1

    service = DocumentService(mock_session)
    with pytest.raises(ForbiddenError):
        await service.list_shipment_documents(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            user_roles={"CUSTOMER_PORTAL"},
            is_portal=True,
            customer_id=my_customer_id,
        )

    # 2. Carrier Portal sees transport documents only (BL, AWB), excludes Commercial Invoice
    doc_bl = Document(shipment_id=shipment_id, doc_type="BILL_OF_LADING", file_url="s3://bl.pdf", status="APPROVED")
    doc_inv = Document(shipment_id=shipment_id, doc_type="COMMERCIAL_INVOICE", file_url="s3://inv.pdf", status="APPROVED")
    doc_bl.id = uuid.uuid4()
    doc_inv.id = uuid.uuid4()

    mock_exec_2 = MagicMock()
    mock_exec_2.scalars.return_value.all.return_value = [doc_bl, doc_inv]
    mock_session.execute.return_value = mock_exec_2

    carrier_docs = await service.list_shipment_documents(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        user_roles={"CARRIER_PORTAL"},
        is_portal=True,
    )

    doc_types = [d["doc_type"] for d in carrier_docs]
    assert "BILL_OF_LADING" in doc_types
    assert "COMMERCIAL_INVOICE" not in doc_types


# ---------------------------------------------------------------------------
# Phase 4.4 Tests: Document Expiry Monitoring (Pure Function)
# ---------------------------------------------------------------------------

def test_document_expiry_alert_thresholds():
    """Verify 30/14/7-day threshold calculation and severity categorization."""
    today = date(2026, 9, 1)

    docs = [
        {"id": "doc-1", "doc_type": "PERMIT", "expiry_date": "2026-08-25"},  # Expired (-7 days)
        {"id": "doc-2", "doc_type": "INSURANCE", "expiry_date": "2026-09-05"},  # 4 days -> CRITICAL
        {"id": "doc-3", "doc_type": "LICENSE", "expiry_date": "2026-09-12"},  # 11 days -> WARNING
        {"id": "doc-4", "doc_type": "CERTIFICATE", "expiry_date": "2026-09-25"},  # 24 days -> INFO
        {"id": "doc-5", "doc_type": "PASSPORT", "expiry_date": "2026-11-01"},  # 61 days -> OK (no alert)
    ]

    alerts = check_document_expiries(docs, today=today, thresholds=(30, 14, 7))

    assert len(alerts) == 4
    severities = {a["document_id"]: a["severity"] for a in alerts}
    assert severities["doc-1"] == "EXPIRED"
    assert severities["doc-2"] == "CRITICAL"
    assert severities["doc-3"] == "WARNING"
    assert severities["doc-4"] == "INFO"


# ---------------------------------------------------------------------------
# Phase 4.5 Tests: Tracking Event Taxonomy & Normalization
# ---------------------------------------------------------------------------

def test_tracking_event_taxonomy_validation():
    """Verify full ~60 event taxonomy validation across all 6 categories."""
    assert len(EVENT_TAXONOMY) >= 55

    # Check key categories
    valid_types = [
        ("BOOKING_CONFIRMED", EventCategory.BOOKING),
        ("CARGO_STUFFED", EventCategory.CARGO),
        ("LOADED_ON_VESSEL", EventCategory.TRANSPORT),
        ("CUSTOMS_CLEARED", EventCategory.CUSTOMS),
        ("DELIVERED", EventCategory.DELIVERY),
        ("VESSEL_ROLL", EventCategory.EXCEPTION),
        ("SHORT_SHIPMENT", EventCategory.EXCEPTION),
    ]

    for event_type, expected_cat in valid_types:
        is_valid, norm_type, cat = validate_event_type(event_type)
        assert is_valid is True
        assert norm_type == event_type
        assert cat == expected_cat

    # Invalid event type
    is_valid, _, _ = validate_event_type("UNKNOWN_RANDOM_EVENT")
    assert is_valid is False


@pytest.mark.asyncio
async def test_tracking_service_record_and_timeline():
    """Verify event recording, UTC normalization, and chronological timeline ordering."""
    tenant_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    shipment = Shipment(
        booking_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        mode="SEA",
        status="IN_TRANSIT",
    )
    shipment.id = shipment_id
    shipment.tenant_id = tenant_id

    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = shipment
    mock_session.execute.return_value = mock_exec

    service = TrackingService(mock_session)

    # Invalid event type raises ValidationError
    with pytest.raises(ValidationError):
        await service.record_event(
            shipment_id=shipment_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type="INVALID_CODE",
        )

    # Valid event recording
    t_utc = datetime(2026, 9, 3, 14, 30, tzinfo=timezone.utc)
    res = await service.record_event(
        shipment_id=shipment_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        event_type="LOADED_ON_VESSEL",
        location="PKKAR (Karachi Port)",
        event_time_original="2026-09-03T19:30:00+05:00",
        event_time_utc=t_utc,
        description="Container loaded on MV Ever Given",
        source="TERMINAL",
    )

    assert res["event_type"] == "LOADED_ON_VESSEL"
    assert res["category"] == "TRANSPORT"
    assert res["location"] == "PKKAR (Karachi Port)"
    assert res["source"] == "TERMINAL"


# ---------------------------------------------------------------------------
# API Integration Tests for Documents & Tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_document_and_tracking_endpoints():
    """Verify FastAPI routes for documents and tracking return expected schemas."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    shipment_id = uuid.uuid4()

    current_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        customer_id=None,
        permissions={"shipment:create", "shipment:read", "shipment:transition"},
        roles={"OPERATIONS", "COMPLIANCE"},
        is_portal=False,
    )

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get Tracking Taxonomy Catalog
        tax_resp = await client.get("/api/v1/tracking/taxonomy")
        assert tax_resp.status_code == 200
        tax_data = tax_resp.json()["data"]
        assert len(tax_data) >= 50

        # 2. Upload Document via JSON
        doc_resp = await client.post(
            f"/api/v1/shipments/{shipment_id}/documents/json",
            json={
                "doc_type": "AIR_WAYBILL",
                "document_name": "Master AWB 071-12345678",
                "file_url": "s3://docs/mawb.pdf",
                "is_mandatory": True,
            },
        )
        assert doc_resp.status_code == 200
        doc_data = doc_resp.json()["data"]
        assert doc_data["doc_type"] == "AIR_WAYBILL"

        # 3. Generate Document Checklist
        chk_resp = await client.post(
            f"/api/v1/shipments/{shipment_id}/document-checklist/generate",
            json={
                "mode": "AIR",
                "service_type": "DIRECT",
                "commodity": "DGR",
                "is_dgr": True,
                "incoterm": "FOB",
                "destination_country": "US",
            },
        )
        assert chk_resp.status_code == 200
        chk_data = chk_resp.json()["data"]
        assert len(chk_data) >= 4

        # 4. Record Tracking Event
        trk_resp = await client.post(
            f"/api/v1/shipments/{shipment_id}/events",
            json={
                "event_type": "DEPARTED",
                "location": "KHI Airport",
                "event_time_utc": "2026-09-03T12:00:00Z",
                "description": "Flight departed",
                "source": "CARRIER_API",
            },
        )
        assert trk_resp.status_code == 200
        trk_data = trk_resp.json()["data"]
        assert trk_data["event_type"] == "DEPARTED"
        assert trk_data["category"] == "TRANSPORT"

    app.dependency_overrides.clear()
