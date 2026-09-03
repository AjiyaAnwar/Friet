import pytest
import uuid
from app.services.cargo_acceptance import CargoAcceptanceService
from app.schemas.cargo import CargoAcceptanceRequest
from app.core.exceptions import ValidationError

@pytest.mark.asyncio
async def test_cargo_acceptance_short_shipment(db_session):
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = CargoAcceptanceService(db_session)
    
    payload = CargoAcceptanceRequest(
        warehouse="LHR_MAIN",
        booked_pieces=10,
        pieces_received=8,
        pieces_accepted=8,
        booked_weight=100.0,
        actual_weight=80.0,
        condition="SHORT",
        screening_status="NOT_REQUIRED",
        damage_notes="2 pieces missing from pallet"
    )
    
    result = await service.process_acceptance(shipment_id, tenant_id, actor_id, payload)
    
    assert result["status"] == "ACCEPTED"
    assert result["exception_generated"] is not None
    assert result["exception_generated"]["exception_type"] == "SHORT_SHIPMENT"

@pytest.mark.asyncio
async def test_cargo_acceptance_validation(db_session):
    tenant_id = uuid.uuid4()
    shipment_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    service = CargoAcceptanceService(db_session)
    
    payload = CargoAcceptanceRequest(
        warehouse="LHR_MAIN",
        booked_pieces=10,
        pieces_received=10,
        pieces_accepted=12,  # Invalid
        booked_weight=100.0,
        actual_weight=100.0,
        condition="OK",
        screening_status="NOT_REQUIRED"
    )
    
    with pytest.raises(ValidationError):
        await service.process_acceptance(shipment_id, tenant_id, actor_id, payload)
