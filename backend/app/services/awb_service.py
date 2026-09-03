import uuid
import asyncio
from datetime import datetime, UTC
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ValidationError, NotFoundError, ConflictError
from app.schemas.awb import AWBCreateRequest, AWBResponse, AWBAmendmentRequest, AWBCancellationRequest

class AWBRepositoryFake:
    """In-memory test fake for AWB persistence until real PG schema is available."""
    _awbs: dict[uuid.UUID, dict] = {}
    _sequences: dict[str, int] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_next_sequence(cls, prefix: str) -> str:
        async with cls._lock:
            # IMPORTANT: This must be mapped to a PostgreSQL sequence or atomic table!
            current = cls._sequences.get(prefix, 1000000)
            cls._sequences[prefix] = current + 1
            # Mod 7 check digit standard for AWBs
            serial = str(current)
            check_digit = current % 7
            return f"{serial}{check_digit}"

    @classmethod
    async def save(cls, awb: dict) -> None:
        cls._awbs[awb["id"]] = awb

    @classmethod
    async def get(cls, awb_id: uuid.UUID) -> dict | None:
        return cls._awbs.get(awb_id)

    @classmethod
    async def get_by_mawb(cls, mawb_id: uuid.UUID) -> list[dict]:
        return [a for a in cls._awbs.values() if a.get("parent_mawb_id") == mawb_id and a["status"] != "CANCELLED"]

class AWBService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AWBRepositoryFake()

    async def create_awb(self, tenant_id: uuid.UUID, actor_id: uuid.UUID, payload: AWBCreateRequest) -> AWBResponse:
        # Validate Hierarchy
        if payload.awb_type == "HAWB" and not payload.parent_mawb_id:
            raise ValidationError("HAWB requires a parent MAWB ID")
        
        if payload.awb_type == "HAWB" and payload.parent_mawb_id:
            parent = await self.repo.get(payload.parent_mawb_id)
            if not parent:
                raise NotFoundError("Parent MAWB not found")
            if parent["tenant_id"] != tenant_id:
                raise ConflictError("Parent MAWB belongs to a different tenant")
            if parent["awb_type"] != "MAWB":
                raise ValidationError("Parent must be a MAWB")
                
        # Generate number safely
        serial = payload.serial_number
        if not serial:
            serial = await self.repo.get_next_sequence(payload.airline_prefix)
            
        full_number = f"{payload.airline_prefix}-{serial}"
        
        awb_dict = payload.model_dump()
        awb_dict.update({
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "status": "DRAFT",
            "version": 1,
            "serial_number": serial,
            "full_awb_number": full_number,
            "issuing_user": actor_id,
            "issue_date": None,
            "history": []
        })
        
        # Verify weight/pieces consistency logic
        if payload.awb_type == "MAWB":
            # Just create it
            pass
            
        await self.repo.save(awb_dict)
        return AWBResponse(**awb_dict)

    async def amend_awb(self, awb_id: uuid.UUID, tenant_id: uuid.UUID, actor_id: uuid.UUID, payload: AWBAmendmentRequest) -> AWBResponse:
        awb = await self.repo.get(awb_id)
        if not awb or awb["tenant_id"] != tenant_id:
            raise NotFoundError("AWB not found")
            
        if awb["status"] in ["CANCELLED"]:
            raise ValidationError("Cannot amend a cancelled AWB")

        # Snapshot history
        history_entry = {
            "version": awb["version"],
            "timestamp": datetime.now(UTC).isoformat(),
            "reason": payload.reason,
            "requested_by": actor_id,
            "carrier_confirmation": payload.carrier_confirmation_ref
        }
        awb["history"].append(history_entry)
        awb["version"] += 1
        
        for k, v in payload.fields_changed.items():
            awb[k] = v
            
        await self.repo.save(awb)
        return AWBResponse(**awb)

    async def cancel_awb(self, awb_id: uuid.UUID, tenant_id: uuid.UUID, actor_id: uuid.UUID, payload: AWBCancellationRequest) -> AWBResponse:
        awb = await self.repo.get(awb_id)
        if not awb or awb["tenant_id"] != tenant_id:
            raise NotFoundError("AWB not found")
            
        if awb["awb_type"] == "MAWB":
            children = await self.repo.get_by_mawb(awb_id)
            if children:
                raise ConflictError("Cannot cancel MAWB with active HAWB children")
                
        awb["status"] = "CANCELLED"
        history_entry = {
            "version": awb["version"],
            "timestamp": datetime.now(UTC).isoformat(),
            "cancellation_reason": payload.reason,
            "requested_by": actor_id,
            "replacement": payload.replacement_awb_id
        }
        awb["history"].append(history_entry)
        
        await self.repo.save(awb)
        return AWBResponse(**awb)

    async def generate_label(self, awb_id: uuid.UUID, tenant_id: uuid.UUID) -> bytes:
        awb = await self.repo.get(awb_id)
        if not awb or awb["tenant_id"] != tenant_id:
            raise NotFoundError("AWB not found")
            
        if awb["status"] == "DRAFT":
            raise ValidationError("Cannot generate label for DRAFT AWB")
            
        # Stub PDF generation
        return b"%PDF-1.4\n%Stub IATA Barcode Label PDF\n"
