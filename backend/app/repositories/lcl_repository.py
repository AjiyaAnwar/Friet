from typing import Sequence, Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.team3_entities import BillOfLading, SeaConsolidation
from app.schemas.lcl import ConsolidationCreate, ConsolidationResponse
import uuid

class LCLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pending_hbls(self) -> Sequence[BillOfLading]:
        stmt = select(BillOfLading).where(BillOfLading.bl_type == "HOUSE")
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_available_mbls(self) -> Sequence[BillOfLading]:
        stmt = select(BillOfLading).where(BillOfLading.bl_type == "MASTER")
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def create_consolidation(self, data: ConsolidationCreate) -> SeaConsolidation:
        record = SeaConsolidation(
            master_bl_id=uuid.UUID(data.mbl_id),
            status="CONSOLIDATED"
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_consolidation(self, consolidation_id: str) -> Optional[SeaConsolidation]:
        stmt = select(SeaConsolidation).where(SeaConsolidation.id == uuid.UUID(consolidation_id))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
