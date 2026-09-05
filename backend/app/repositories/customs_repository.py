from typing import Sequence, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.team3_entities import CustomsDeclaration
from app.schemas.customs import CustomsDeclarationCreate
import uuid

class CustomsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def create(self, shipment_id: str, declaration: CustomsDeclarationCreate) -> CustomsDeclaration:
        record = CustomsDeclaration(
            shipment_id=uuid.UUID(shipment_id),
            status="PENDING",
            hs_code="0000.00"
        )
        self.session.add(record)
        await self.session.flush()
        return record
        
    async def get(self, id: str) -> Optional[CustomsDeclaration]:
        stmt = select(CustomsDeclaration).where(CustomsDeclaration.id == uuid.UUID(id))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
        
    async def list_by_shipment(self, shipment_id: str) -> Sequence[CustomsDeclaration]:
        stmt = select(CustomsDeclaration).where(CustomsDeclaration.shipment_id == uuid.UUID(shipment_id))
        res = await self.session.execute(stmt)
        return res.scalars().all()
        
    async def update_status(self, id: str, status: str) -> Optional[CustomsDeclaration]:
        record = await self.get(id)
        if record:
            record.status = status
            await self.session.flush()
        return record
