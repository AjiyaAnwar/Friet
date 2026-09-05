import pytest
from decimal import Decimal
from app.schemas.customs import CustomsDeclarationCreate, ClearanceStatus
from app.repositories.customs_repository import FakeCustomsRepository
from app.services.customs_service import CustomsService

@pytest.fixture
def customs_service():
    repo = FakeCustomsRepository()
    return CustomsService(repository=repo)

def test_create_declaration_cleared(customs_service):
    declaration = CustomsDeclarationCreate(
        declared_value=Decimal("500.00"),
        currency="USD",
        hs_code="123456",
        origin_country="CA",
        destination_country="US",
        description="Normal goods"
    )
    result = customs_service.create_declaration("ship-123", declaration)
    assert result.status == ClearanceStatus.CLEARED
    assert result.shipment_id == "ship-123"

def test_create_declaration_under_review(customs_service):
    declaration = CustomsDeclarationCreate(
        declared_value=Decimal("3000.00"),
        currency="USD",
        hs_code="123456",
        origin_country="CA",
        destination_country="US",
        description="Expensive goods"
    )
    result = customs_service.create_declaration("ship-124", declaration)
    assert result.status == ClearanceStatus.UNDER_REVIEW

def test_create_declaration_sanctions_rejected(customs_service):
    declaration = CustomsDeclarationCreate(
        declared_value=Decimal("100.00"),
        currency="USD",
        hs_code="123456",
        origin_country="CA",
        destination_country="US",
        description="Contains WEAPONS"
    )
    result = customs_service.create_declaration("ship-125", declaration)
    assert result.status == ClearanceStatus.REJECTED

def test_update_status(customs_service):
    declaration = CustomsDeclarationCreate(
        declared_value=Decimal("3000.00"),
        currency="USD",
        hs_code="123456",
        origin_country="CA",
        destination_country="US",
        description="Expensive goods"
    )
    result = customs_service.create_declaration("ship-126", declaration)
    assert result.status == ClearanceStatus.UNDER_REVIEW
    
    updated = customs_service.update_clearance_status(result.id, ClearanceStatus.CLEARED)
    assert updated.status == ClearanceStatus.CLEARED
