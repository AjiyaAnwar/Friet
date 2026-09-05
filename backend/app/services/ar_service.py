import uuid
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException

from app.schemas.ar import (
    ARAgingReport,
    CustomerAgingSummary,
    InvoiceSummary,
    PaymentCreate,
    PaymentResponse,
    PaymentAllocationRequest,
    PaymentAllocationResponse,
    AllocationRecord
)
from app.repositories.ar_repository import (
    ar_repo,
    PaymentModel,
    PaymentAllocationModel,
    InvoiceModel,
    DunningLogModel
)
from app.db.models.events import OutboxEvent # Ensure we mock publishing an event

class ARService:
    def __init__(self, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = ar_repo
        
    def _get_bucket(self, due_date: datetime, as_of: datetime) -> str:
        if due_date >= as_of:
            return "current"
        days_overdue = (as_of - due_date).days
        if days_overdue <= 30:
            return "days_1_30"
        elif days_overdue <= 60:
            return "days_31_60"
        elif days_overdue <= 90:
            return "days_61_90"
        elif days_overdue <= 120:
            return "days_91_120"
        else:
            return "days_120_plus"

    async def get_aging_report(self, as_of_date: datetime, currency: str, customer_id: Optional[uuid.UUID] = None) -> ARAgingReport:
        invoices = await self.repo.get_active_invoices(self.tenant_id, customer_id, currency)
        
        customer_map = {}
        grand_total = Decimal('0.00')
        
        for inv in invoices:
            outstanding = inv.total_amount - inv.paid_amount
            if outstanding <= 0:
                continue
                
            bucket = self._get_bucket(inv.due_date, as_of_date)
            inv_summary = InvoiceSummary(
                invoice_id=inv.id,
                tenant_id=inv.tenant_id,
                customer_id=inv.customer_id,
                currency=inv.currency,
                total_amount=inv.total_amount,
                paid_amount=inv.paid_amount,
                outstanding_balance=outstanding,
                due_date=inv.due_date,
                status=inv.status,
                bucket=bucket
            )
            
            if inv.customer_id not in customer_map:
                customer_map[inv.customer_id] = CustomerAgingSummary(
                    customer_id=inv.customer_id,
                    currency=inv.currency,
                    invoices=[]
                )
                
            summary = customer_map[inv.customer_id]
            summary.invoices.append(inv_summary)
            summary.total_outstanding += outstanding
            setattr(summary, bucket, getattr(summary, bucket) + outstanding)
            grand_total += outstanding

        return ARAgingReport(
            as_of_date=as_of_date,
            tenant_id=self.tenant_id,
            currency=currency,
            grand_total_outstanding=grand_total,
            customer_summaries=list(customer_map.values())
        )

    async def record_payment(self, payload: PaymentCreate) -> PaymentResponse:
        payment = PaymentModel(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            customer_id=payload.customer_id,
            amount=payload.amount,
            unallocated_amount=payload.amount,
            currency=payload.currency,
            payment_date=payload.payment_date,
            bank_reference=payload.bank_reference,
            idempotency_key=payload.idempotency_key,
            status="UNALLOCATED",
            created_at=datetime.now(UTC),
            created_by=self.user_id
        )
        saved = await self.repo.save_payment(payment)
        
        return PaymentResponse(
            id=saved.id,
            customer_id=saved.customer_id,
            amount=saved.amount,
            currency=saved.currency,
            unallocated_amount=saved.unallocated_amount,
            payment_date=saved.payment_date,
            bank_reference=saved.bank_reference,
            status=saved.status,
            created_at=saved.created_at,
            created_by=saved.created_by
        )

    async def allocate_payment(self, payment_id: uuid.UUID, payload: PaymentAllocationRequest) -> PaymentAllocationResponse:
        await self.repo.acquire_lock()
        try:
            payment = await self.repo.get_payment_by_id(payment_id)
            if not payment or payment.tenant_id != self.tenant_id:
                raise HTTPException(status_code=404, detail="Payment not found")
                
            if payment.unallocated_amount <= 0:
                raise HTTPException(status_code=400, detail="Payment fully allocated")

            # Get customer invoices matching currency
            invoices = await self.repo.get_active_invoices(self.tenant_id, payment.customer_id, payment.currency)
            invoices = [inv for inv in invoices if (inv.total_amount - inv.paid_amount) > 0]
            
            allocations = []
            total_allocated = Decimal('0.00')
            
            if payload.allocation_type == "MANUAL" and payload.manual_allocations:
                for req_alloc in payload.manual_allocations:
                    inv = next((i for i in invoices if i.id == req_alloc.invoice_id), None)
                    if not inv:
                        raise HTTPException(status_code=400, detail=f"Invoice {req_alloc.invoice_id} not found or invalid")
                        
                    outstanding = inv.total_amount - inv.paid_amount
                    if req_alloc.amount > outstanding:
                        raise HTTPException(status_code=400, detail=f"Amount exceeds outstanding balance for invoice {inv.id}")
                        
                    if req_alloc.amount > (payment.unallocated_amount - total_allocated):
                        raise HTTPException(status_code=400, detail="Total allocation exceeds payment unallocated amount")
                        
                    alloc_amt = req_alloc.amount
                    inv.paid_amount += alloc_amt
                    if inv.paid_amount == inv.total_amount:
                        inv.status = "PAID"
                    else:
                        inv.status = "PARTIAL"
                        
                    total_allocated += alloc_amt
                    allocations.append((inv, alloc_amt))
            else:
                # AUTO (FIFO or LIFO)
                reverse_sort = True if payload.allocation_type == "LIFO" else False
                invoices.sort(key=lambda x: x.due_date, reverse=reverse_sort)
                
                remaining_to_allocate = payment.unallocated_amount
                for inv in invoices:
                    if remaining_to_allocate <= 0:
                        break
                    outstanding = inv.total_amount - inv.paid_amount
                    alloc_amt = min(outstanding, remaining_to_allocate)
                    
                    inv.paid_amount += alloc_amt
                    if inv.paid_amount == inv.total_amount:
                        inv.status = "PAID"
                    else:
                        inv.status = "PARTIAL"
                        
                    remaining_to_allocate -= alloc_amt
                    total_allocated += alloc_amt
                    allocations.append((inv, alloc_amt))
                    
            if total_allocated == 0:
                raise HTTPException(status_code=400, detail="No eligible invoices for allocation")

            payment.unallocated_amount -= total_allocated
            if payment.unallocated_amount == 0:
                payment.status = "ALLOCATED"
            else:
                payment.status = "PARTIAL"

            await self.repo.update_payment(payment)
            
            result_allocations = []
            for inv, amt in allocations:
                await self.repo.update_invoice(inv)
                record = PaymentAllocationModel(
                    id=uuid.uuid4(),
                    tenant_id=self.tenant_id,
                    payment_id=payment.id,
                    invoice_id=inv.id,
                    amount=amt,
                    allocated_at=datetime.now(UTC),
                    created_by=self.user_id
                )
                await self.repo.save_allocation(record)
                result_allocations.append(AllocationRecord(
                    allocation_id=record.id,
                    invoice_id=record.invoice_id,
                    allocated_amount=record.amount
                ))

            return PaymentAllocationResponse(
                payment_id=payment.id,
                total_allocated=total_allocated,
                remaining_unallocated=payment.unallocated_amount,
                allocations=result_allocations
            )
        finally:
            await self.repo.release_lock()

class DunningService:
    def __init__(self, tenant_id: uuid.UUID):
        self.tenant_id = tenant_id
        self.repo = ar_repo

    async def run_dunning(self, as_of_date: datetime):
        invoices = await self.repo.get_active_invoices(self.tenant_id)
        
        for inv in invoices:
            if inv.status in ("PAID", "VOID", "CANCELLED", "DISPUTED", "ON_HOLD"):
                continue
            
            outstanding = inv.total_amount - inv.paid_amount
            if outstanding <= 0:
                continue

            days_overdue = (as_of_date - inv.due_date).days
            
            stage = None
            if days_overdue >= 60:
                stage = "60_DAYS_LETTER"
            elif days_overdue >= 30:
                stage = "30_DAYS_ALERT"
            elif days_overdue >= 14:
                stage = "14_DAYS_REMINDER_2"
            elif days_overdue >= 7:
                stage = "7_DAYS_REMINDER_1"
                
            if not stage:
                continue

            idempotency_key = f"{inv.id}-{stage}-{inv.due_date.date()}"
            existing_log = await self.repo.get_dunning_log(idempotency_key)
            if existing_log:
                continue # Already sent this stage
                
            # Create outbox event in a real system here
            # event = OutboxEvent(aggregate_type="DUNNING", event_type=stage, payload={"invoice_id": str(inv.id)})
            
            log = DunningLogModel(
                id=uuid.uuid4(),
                tenant_id=self.tenant_id,
                invoice_id=inv.id,
                stage=stage,
                sent_at=datetime.now(UTC),
                status="SENT",
                idempotency_key=idempotency_key
            )
            await self.repo.save_dunning_log(log)
