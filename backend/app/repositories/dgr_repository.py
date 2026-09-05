from typing import Sequence, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.team3_entities import DGRDeclaration, DGRApproval

class DGRRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_item(self, item: DGRDeclaration) -> DGRDeclaration:
        self.session.add(item)
        await self.session.flush()
        return item
        
    async def get_item(self, item_id: uuid.UUID) -> Optional[DGRDeclaration]:
        stmt = select(DGRDeclaration).where(DGRDeclaration.id == item_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
        
    async def get_items_by_shipment(self, shipment_id: uuid.UUID) -> Sequence[DGRDeclaration]:
        stmt = select(DGRDeclaration).where(DGRDeclaration.shipment_id == shipment_id)
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def save_approval(self, apprv: DGRApproval) -> DGRApproval:
        self.session.add(apprv)
        await self.session.flush()
        return apprv
