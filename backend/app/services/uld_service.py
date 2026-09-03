import uuid
import asyncio
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ValidationError, NotFoundError
from app.schemas.flight import ULDCreateRequest, ULDResponse, ULDAllocation, FlightManifestResponse

class ULDRepositoryFake:
    _ulds: dict[uuid.UUID, dict] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def save(cls, uld: dict) -> None:
        async with cls._lock:
            cls._ulds[uld["id"]] = uld

    @classmethod
    async def get(cls, uld_id: uuid.UUID) -> dict | None:
        return cls._ulds.get(uld_id)

    @classmethod
    async def get_by_flight(cls, flight_id: uuid.UUID) -> list[dict]:
        return [u for u in cls._ulds.values() if u["flight_id"] == flight_id]

class ULDService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ULDRepositoryFake()

    async def create_uld(self, tenant_id: uuid.UUID, payload: ULDCreateRequest) -> ULDResponse:
        uld_dict = payload.model_dump()
        uld_dict.update({
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "build_status": "OPEN",
            "allocations": [],
            "total_pieces": 0,
            "total_weight": 0.0
        })
        await self.repo.save(uld_dict)
        return ULDResponse(**uld_dict)

    async def assign_awb_to_uld(self, tenant_id: uuid.UUID, uld_id: uuid.UUID, allocation: ULDAllocation) -> ULDResponse:
        uld = await self.repo.get(uld_id)
        if not uld or uld["tenant_id"] != tenant_id:
            raise NotFoundError("ULD not found")
            
        if uld["build_status"] != "OPEN":
            raise ValidationError("Cannot assign AWB to finalized ULD")
            
        # Check capacity
        if uld["total_weight"] + allocation.weight > uld["max_weight"]:
            raise ValidationError("ULD weight capacity exceeded")
            
        # Over-allocation checks (mocked: in a real system we'd check if AWB is fully allocated across all ULDs)
        
        uld["allocations"].append(allocation.model_dump())
        uld["total_pieces"] += allocation.pieces
        uld["total_weight"] += allocation.weight
        
        await self.repo.save(uld)
        return ULDResponse(**uld)

    async def finalize_uld(self, tenant_id: uuid.UUID, uld_id: uuid.UUID) -> ULDResponse:
        uld = await self.repo.get(uld_id)
        if not uld or uld["tenant_id"] != tenant_id:
            raise NotFoundError("ULD not found")
            
        uld["build_status"] = "FINALIZED"
        await self.repo.save(uld)
        return ULDResponse(**uld)

    async def generate_flight_manifest(self, tenant_id: uuid.UUID, flight_id: uuid.UUID) -> FlightManifestResponse:
        ulds = await self.repo.get_by_flight(flight_id)
        tenant_ulds = [u for u in ulds if u["tenant_id"] == tenant_id]
        
        total_awbs = 0
        total_pieces = 0
        total_weight = 0.0
        
        awb_set = set()
        
        for uld in tenant_ulds:
            for alloc in uld["allocations"]:
                awb_set.add(alloc["awb_id"])
                total_pieces += alloc["pieces"]
                total_weight += alloc["weight"]
                
        total_awbs = len(awb_set)
        
        return FlightManifestResponse(
            flight_id=flight_id,
            tenant_id=tenant_id,
            version=1,
            generated_at=datetime.now(UTC),
            ulds=[ULDResponse(**u) for u in tenant_ulds],
            awbs_loose=[],
            total_awbs=total_awbs,
            total_pieces=total_pieces,
            total_weight=total_weight
        )
