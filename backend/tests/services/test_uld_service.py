import pytest
import uuid
from app.services.uld_service import ULDService
from app.schemas.flight import ULDCreateRequest, ULDAllocation
from app.core.exceptions import ValidationError

@pytest.mark.asyncio
async def test_uld_create_and_assign(db_session):
    tenant_id = uuid.uuid4()
    flight_id = uuid.uuid4()
    service = ULDService(db_session)
    
    payload = ULDCreateRequest(
        uld_number="AKE12345BA",
        uld_type="AKE",
        flight_id=flight_id,
        max_weight=1500.0,
        max_volume=4.3
    )
    uld = await service.create_uld(tenant_id, payload)
    
    assert uld.build_status == "OPEN"
    
    awb_id = uuid.uuid4()
    alloc = ULDAllocation(awb_id=awb_id, pieces=10, weight=500.0)
    uld = await service.assign_awb_to_uld(tenant_id, uld.id, alloc)
    
    assert uld.total_pieces == 10
    assert uld.total_weight == 500.0

@pytest.mark.asyncio
async def test_uld_capacity_exceeded(db_session):
    tenant_id = uuid.uuid4()
    flight_id = uuid.uuid4()
    service = ULDService(db_session)
    
    payload = ULDCreateRequest(
        uld_number="AKE12345BA",
        uld_type="AKE",
        flight_id=flight_id,
        max_weight=100.0, # low capacity
        max_volume=4.3
    )
    uld = await service.create_uld(tenant_id, payload)
    
    alloc = ULDAllocation(awb_id=uuid.uuid4(), pieces=10, weight=150.0) # Exceeds 100.0
    
    with pytest.raises(ValidationError):
        await service.assign_awb_to_uld(tenant_id, uld.id, alloc)

@pytest.mark.asyncio
async def test_flight_manifest_totals(db_session):
    tenant_id = uuid.uuid4()
    flight_id = uuid.uuid4()
    service = ULDService(db_session)
    
    uld_payload = ULDCreateRequest(
        uld_number="AKE12345BA",
        uld_type="AKE",
        flight_id=flight_id,
        max_weight=1500.0,
        max_volume=4.3
    )
    uld = await service.create_uld(tenant_id, uld_payload)
    
    awb1 = uuid.uuid4()
    awb2 = uuid.uuid4()
    
    await service.assign_awb_to_uld(tenant_id, uld.id, ULDAllocation(awb_id=awb1, pieces=10, weight=500.0))
    await service.assign_awb_to_uld(tenant_id, uld.id, ULDAllocation(awb_id=awb2, pieces=5, weight=250.0))
    
    manifest = await service.generate_flight_manifest(tenant_id, flight_id)
    
    assert manifest.total_awbs == 2
    assert manifest.total_pieces == 15
    assert manifest.total_weight == 750.0
