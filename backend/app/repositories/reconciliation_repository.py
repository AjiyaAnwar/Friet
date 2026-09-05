from typing import Sequence
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.domain import Invoice, CostLine, PayablePayment

class ReconciliationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_invoices_for_period(self, start: datetime, end: datetime) -> Sequence[Invoice]:
        stmt = select(Invoice).where(Invoice.created_at >= start, Invoice.created_at <= end)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_costs_for_period(self, start: datetime, end: datetime) -> Sequence[CostLine]:
        stmt = select(CostLine).where(CostLine.created_at >= start, CostLine.created_at <= end)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_payments_for_period(self, start: datetime, end: datetime) -> Sequence[PayablePayment]:
        stmt = select(PayablePayment).where(PayablePayment.created_at >= start, PayablePayment.created_at <= end)
        result = await self.session.execute(stmt)
        return result.scalars().all()
