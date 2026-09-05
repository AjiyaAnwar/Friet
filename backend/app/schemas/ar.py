from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
import uuid

class InvoiceSummary(BaseModel):
    invoice_id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    currency: str
    total_amount: Decimal
    paid_amount: Decimal
    outstanding_balance: Decimal
    due_date: datetime
    status: str
    bucket: str  # 'current', 'days_1_30', 'days_31_60', 'days_61_90', 'days_91_120', 'days_120_plus'

class CustomerAgingSummary(BaseModel):
    customer_id: uuid.UUID
    currency: str
    current: Decimal = Decimal('0.00')
    days_1_30: Decimal = Decimal('0.00')
    days_31_60: Decimal = Decimal('0.00')
    days_61_90: Decimal = Decimal('0.00')
    days_91_120: Decimal = Decimal('0.00')
    days_120_plus: Decimal = Decimal('0.00')
    total_outstanding: Decimal = Decimal('0.00')
    invoices: Optional[List[InvoiceSummary]] = None

class ARAgingReport(BaseModel):
    as_of_date: datetime
    tenant_id: uuid.UUID
    currency: str
    grand_total_outstanding: Decimal = Decimal('0.00')
    customer_summaries: List[CustomerAgingSummary]

class PaymentCreate(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal = Field(..., gt=0, description="Amount must be positive")
    currency: str = Field(..., min_length=3, max_length=3)
    payment_date: datetime
    bank_reference: str
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    idempotency_key: Optional[str] = None

class PaymentResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    amount: Decimal
    currency: str
    unallocated_amount: Decimal
    payment_date: datetime
    bank_reference: str
    status: str
    created_at: datetime
    created_by: Optional[uuid.UUID] = None

class ManualAllocation(BaseModel):
    invoice_id: uuid.UUID
    amount: Decimal = Field(..., gt=0)

class PaymentAllocationRequest(BaseModel):
    allocation_type: str = Field(..., description="MANUAL, FIFO, or LIFO")
    manual_allocations: Optional[List[ManualAllocation]] = None

class AllocationRecord(BaseModel):
    allocation_id: uuid.UUID
    invoice_id: uuid.UUID
    allocated_amount: Decimal

class PaymentAllocationResponse(BaseModel):
    payment_id: uuid.UUID
    total_allocated: Decimal
    remaining_unallocated: Decimal
    allocations: List[AllocationRecord]
    
class DunningLogResponse(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    stage: str
    sent_at: datetime
    status: str
