from typing import Sequence, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.domain import Invoice
from app.db.models.team3_entities import ARPayment

class ARRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.lock = False

    async def get_active_invoices(self, tenant_id: uuid.UUID, customer_id: Optional[uuid.UUID] = None, currency: Optional[str] = None) -> Sequence[Invoice]:
        stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
        # Assuming domain.py has status on Invoice or similar logic
        res = await self.session.execute(stmt)
        return res.scalars().all()
        
    async def get_invoice_by_id(self, invoice_id: uuid.UUID) -> Optional[Invoice]:
        stmt = select(Invoice).where(Invoice.id == invoice_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_payment(self, payment: ARPayment) -> ARPayment:
        self.session.add(payment)
        await self.session.flush()
        return payment
        
    async def get_payment_by_id(self, payment_id: uuid.UUID) -> Optional[ARPayment]:
        stmt = select(ARPayment).where(ARPayment.id == payment_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()
        
    async def update_invoice(self, invoice: Invoice):
        self.session.add(invoice)
        await self.session.flush()

    async def update_payment(self, payment: ARPayment):
        self.session.add(payment)
        await self.session.flush()

    async def acquire_lock(self):
        self.lock = True
        
    async def release_lock(self):
        self.lock = False
