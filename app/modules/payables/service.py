"""Accounts Payable and Carrier Cost Verification Service (Phase 5.3).

Integrates carrier/vendor bill recording, automated cost verification against Cost Ledger,
variance handling and exception raising, AP approval workflows, payment recording,
and immutable financial entry management.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.models.commercial import Vendor
from app.db.models.domain import CostLine, Payable, PayableLine, PayablePayment, Shipment, ShipmentException
from app.db.models.financial import FinancialEntry
from app.db.models.reference import Carrier
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService


class PayableService:
    """Core domain service for Accounts Payable & Carrier Cost Verification."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    # -----------------------------------------------------------------------
    # Helper: Validate tenant shipment
    # -----------------------------------------------------------------------
    async def _get_tenant_shipment(self, shipment_id: uuid.UUID, tenant_id: uuid.UUID) -> Shipment:
        if not self.session:
            raise ValidationError("Database session required")
        stmt = select(Shipment).where(Shipment.id == shipment_id, Shipment.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        shipment = res.scalar_one_or_none()
        if not shipment:
            raise NotFoundError(f"Shipment {shipment_id} not found or does not belong to tenant.")
        return shipment

    # -----------------------------------------------------------------------
    # 5.3.2 & 5.3.4 Record Carrier/Vendor Cost Bill & Cost Matching
    # -----------------------------------------------------------------------
    async def record_payable(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        shipment_id: uuid.UUID,
        bill_number: str,
        lines: list[dict[str, Any]],
        vendor_id: uuid.UUID | None = None,
        carrier_id: uuid.UUID | None = None,
        bill_date: date | None = None,
        due_date: date | None = None,
        currency_code: str = "USD",
        tax_amount: float = 0.0,
        supporting_document_url: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record carrier/vendor bill against a shipment and its Cost Ledger."""
        if not self.session:
            raise ValidationError("Database session required")

        shipment = await self._get_tenant_shipment(shipment_id, tenant_id)

        # Validate vendor if provided
        if vendor_id:
            v_stmt = select(Vendor).where(Vendor.id == vendor_id, Vendor.tenant_id == tenant_id)
            v_res = await self.session.execute(v_stmt)
            if not v_res.scalar_one_or_none():
                raise NotFoundError(f"Vendor {vendor_id} not found or does not belong to tenant.")

        # Validate carrier if provided
        if carrier_id:
            c_stmt = select(Carrier).where(Carrier.id == carrier_id)
            c_res = await self.session.execute(c_stmt)
            if not c_res.scalar_one_or_none():
                raise NotFoundError(f"Carrier {carrier_id} not found.")

        # 5.3.4 Duplicate bill check
        existing_stmt = select(Payable).where(
            Payable.tenant_id == tenant_id,
            Payable.bill_number == bill_number.strip(),
        )
        existing_res = await self.session.execute(existing_stmt)
        if existing_res.scalar_one_or_none():
            raise ConflictError(f"Payable bill number '{bill_number}' already exists for this tenant.")

        if not lines:
            raise ValidationError("At least one bill line is required.")

        today = bill_date or date.today()
        subtotal = 0.0
        total_variance = 0.0
        payable_lines_to_add: list[dict[str, Any]] = []

        # Fetch existing shipment cost lines for auto-matching
        cl_stmt = select(CostLine).where(CostLine.shipment_id == shipment_id)
        cl_res = await self.session.execute(cl_stmt)
        cost_lines_map: dict[str, CostLine] = {c.charge_code.upper(): c for c in cl_res.scalars().all() if c.charge_code}

        for l_data in lines:
            charge_code = l_data["charge_code"].strip().upper()
            billed_amount = float(l_data["billed_amount"])
            if billed_amount <= 0:
                raise ValidationError(f"Billed amount for {charge_code} must be positive.")

            subtotal += billed_amount
            cost_line_id = l_data.get("cost_line_id")
            matched_cl: CostLine | None = None

            if cost_line_id:
                cl_by_id_stmt = select(CostLine).where(CostLine.id == cost_line_id, CostLine.shipment_id == shipment_id)
                cl_by_id_res = await self.session.execute(cl_by_id_stmt)
                matched_cl = cl_by_id_res.scalar_one_or_none()
                if not matched_cl:
                    raise NotFoundError(f"Cost line {cost_line_id} does not belong to shipment {shipment_id}.")
            else:
                matched_cl = cost_lines_map.get(charge_code)

            if matched_cl:
                expected_amount = float(matched_cl.amount)
                variance = round(billed_amount - expected_amount, 2)
                if variance == 0:
                    status = "MATCHED"
                elif variance > 0:
                    status = "OVER_BILLED"
                else:
                    status = "UNDER_BILLED"
                
                # Advance CostLine status from ESTIMATED/ACCRUED to BILLED
                if matched_cl.status in {"ESTIMATED", "ACCRUED"}:
                    matched_cl.status = "BILLED"

                payable_lines_to_add.append({
                    "cost_line_id": matched_cl.id,
                    "charge_code": charge_code,
                    "description": l_data.get("description") or matched_cl.description,
                    "quantity": float(l_data.get("quantity", 1.0)),
                    "unit_rate": float(l_data["unit_rate"]) if l_data.get("unit_rate") is not None else billed_amount,
                    "expected_amount": expected_amount,
                    "billed_amount": billed_amount,
                    "variance_amount": variance,
                    "currency_code": currency_code.upper(),
                    "status": status,
                })
                total_variance += variance
            else:
                # Additional charge not previously in Cost Ledger
                # Add new CostLine with is_additional=True and status=BILLED
                new_cl = CostLine(
                    shipment_id=shipment_id,
                    vendor_id=vendor_id,
                    carrier_id=carrier_id,
                    charge_code=charge_code,
                    description=l_data.get("description") or f"Additional billed: {charge_code}",
                    quantity=float(l_data.get("quantity", 1.0)),
                    unit_rate=float(l_data["unit_rate"]) if l_data.get("unit_rate") is not None else billed_amount,
                    amount=billed_amount,
                    currency_code=currency_code.upper(),
                    status="BILLED",
                    is_additional=True,
                    created_by=actor_id,
                )
                self.session.add(new_cl)
                await self.session.flush()

                variance = billed_amount
                total_variance += variance
                payable_lines_to_add.append({
                    "cost_line_id": new_cl.id,
                    "charge_code": charge_code,
                    "description": new_cl.description,
                    "quantity": float(l_data.get("quantity", 1.0)),
                    "unit_rate": float(l_data["unit_rate"]) if l_data.get("unit_rate") is not None else billed_amount,
                    "expected_amount": 0.0,
                    "billed_amount": billed_amount,
                    "variance_amount": variance,
                    "currency_code": currency_code.upper(),
                    "status": "ADDITIONAL_CHARGE",
                })

        total_amount = round(subtotal + float(tax_amount), 2)
        total_variance = round(total_variance, 2)

        payable = Payable(
            tenant_id=tenant_id,
            shipment_id=shipment_id,
            vendor_id=vendor_id,
            carrier_id=carrier_id,
            bill_number=bill_number.strip(),
            bill_date=today,
            due_date=due_date,
            currency_code=currency_code.upper(),
            subtotal_amount=round(subtotal, 2),
            tax_amount=round(float(tax_amount), 2),
            total_amount=total_amount,
            paid_amount=0.0,
            status="RECEIVED",
            verification_status="PENDING",
            approval_status="PENDING",
            variance_amount=total_variance,
            supporting_document_url=supporting_document_url,
            notes=notes,
        )
        self.session.add(payable)
        await self.session.flush()

        for pl_data in payable_lines_to_add:
            pline = PayableLine(
                tenant_id=tenant_id,
                payable_id=payable.id,
                cost_line_id=pl_data["cost_line_id"],
                charge_code=pl_data["charge_code"],
                description=pl_data["description"],
                quantity=pl_data["quantity"],
                unit_rate=pl_data["unit_rate"],
                expected_amount=pl_data["expected_amount"],
                billed_amount=pl_data["billed_amount"],
                variance_amount=pl_data["variance_amount"],
                currency_code=pl_data["currency_code"],
                status=pl_data["status"],
            )
            self.session.add(pline)

        await self.session.flush()

        # Audit Log
        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="payable",
                entity_id=str(payable.id),
                action="payable.created",
                new_value={
                    "bill_number": payable.bill_number,
                    "shipment_id": str(shipment_id),
                    "total_amount": float(payable.total_amount),
                    "variance_amount": float(payable.variance_amount),
                },
            )

        return await self.get_payable(payable.id, tenant_id)

    # -----------------------------------------------------------------------
    # Get & List Payables
    # -----------------------------------------------------------------------
    async def get_payable(self, payable_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Get full details of a payable bill, including lines and payment records."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Payable).where(Payable.id == payable_id, Payable.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        payable = res.scalar_one_or_none()
        if not payable:
            raise NotFoundError(f"Payable {payable_id} not found.")

        # Lines
        l_stmt = select(PayableLine).where(PayableLine.payable_id == payable_id).order_by(PayableLine.created_at.asc())
        l_res = await self.session.execute(l_stmt)
        lines = l_res.scalars().all()

        # Payments
        p_stmt = select(PayablePayment).where(PayablePayment.payable_id == payable_id).order_by(PayablePayment.payment_date.asc())
        p_res = await self.session.execute(p_stmt)
        payments = p_res.scalars().all()

        return {
            "id": str(payable.id),
            "tenant_id": str(payable.tenant_id),
            "shipment_id": str(payable.shipment_id),
            "vendor_id": str(payable.vendor_id) if payable.vendor_id else None,
            "carrier_id": str(payable.carrier_id) if payable.carrier_id else None,
            "bill_number": payable.bill_number,
            "bill_date": payable.bill_date.isoformat(),
            "due_date": payable.due_date.isoformat() if payable.due_date else None,
            "currency_code": payable.currency_code,
            "subtotal_amount": float(payable.subtotal_amount) if payable.subtotal_amount is not None else 0.0,
            "tax_amount": float(payable.tax_amount) if payable.tax_amount is not None else 0.0,
            "total_amount": float(payable.total_amount) if payable.total_amount is not None else 0.0,
            "paid_amount": float(payable.paid_amount) if payable.paid_amount is not None else 0.0,
            "status": payable.status,
            "verification_status": payable.verification_status,
            "approval_status": payable.approval_status,
            "verified_by": str(payable.verified_by) if payable.verified_by else None,
            "verified_at": payable.verified_at.isoformat() if payable.verified_at else None,
            "approved_by": str(payable.approved_by) if payable.approved_by else None,
            "approved_at": payable.approved_at.isoformat() if payable.approved_at else None,
            "rejection_reason": payable.rejection_reason,
            "variance_amount": float(payable.variance_amount) if payable.variance_amount is not None else 0.0,
            "supporting_document_url": payable.supporting_document_url,
            "notes": payable.notes,
            "lines": [
                {
                    "id": str(l.id),
                    "charge_code": l.charge_code,
                    "description": l.description,
                    "quantity": float(l.quantity) if l.quantity is not None else 1.0,
                    "unit_rate": float(l.unit_rate) if l.unit_rate is not None else None,
                    "expected_amount": float(l.expected_amount) if l.expected_amount is not None else 0.0,
                    "billed_amount": float(l.billed_amount) if l.billed_amount is not None else 0.0,
                    "variance_amount": float(l.variance_amount) if l.variance_amount is not None else 0.0,
                    "currency_code": l.currency_code,
                    "status": l.status,
                    "cost_line_id": str(l.cost_line_id) if l.cost_line_id else None,
                }
                for l in lines
            ],
            "payments": [
                {
                    "id": str(p.id),
                    "payment_reference": p.payment_reference,
                    "payment_date": p.payment_date.isoformat(),
                    "amount": float(p.amount) if p.amount is not None else 0.0,
                    "currency_code": p.currency_code,
                    "payment_method": p.payment_method,
                    "recorded_by": str(p.recorded_by),
                    "notes": p.notes,
                }
                for p in payments
            ],
        }

    async def list_payables(
        self,
        *,
        tenant_id: uuid.UUID,
        shipment_id: uuid.UUID | None = None,
        vendor_id: uuid.UUID | None = None,
        carrier_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List tenant payables with optional filtering."""
        if not self.session:
            return []

        stmt = select(Payable).where(Payable.tenant_id == tenant_id)
        if shipment_id:
            stmt = stmt.where(Payable.shipment_id == shipment_id)
        if vendor_id:
            stmt = stmt.where(Payable.vendor_id == vendor_id)
        if carrier_id:
            stmt = stmt.where(Payable.carrier_id == carrier_id)
        if status:
            stmt = stmt.where(Payable.status == status.strip().upper())

        stmt = stmt.order_by(Payable.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        payables = res.scalars().all()

        results = []
        for p in payables:
            results.append({
                "id": str(p.id),
                "bill_number": p.bill_number,
                "bill_date": p.bill_date.isoformat(),
                "shipment_id": str(p.shipment_id),
                "vendor_id": str(p.vendor_id) if p.vendor_id else None,
                "carrier_id": str(p.carrier_id) if p.carrier_id else None,
                "currency_code": p.currency_code,
                "total_amount": float(p.total_amount) if p.total_amount is not None else 0.0,
                "paid_amount": float(p.paid_amount) if p.paid_amount is not None else 0.0,
                "status": p.status,
                "verification_status": p.verification_status,
                "approval_status": p.approval_status,
                "variance_amount": float(p.variance_amount) if p.variance_amount is not None else 0.0,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })
        return results

    # -----------------------------------------------------------------------
    # 5.3.3 & 5.3.6 Cost Verification & Variance Handling
    # -----------------------------------------------------------------------
    async def verify_payable(
        self,
        *,
        payable_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        allow_material_variance: bool = False,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Perform cost verification against the Cost Ledger and detect variances."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Payable).where(Payable.id == payable_id, Payable.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        payable = res.scalar_one_or_none()
        if not payable:
            raise NotFoundError(f"Payable {payable_id} not found.")

        if payable.status in {"APPROVED", "PAID"}:
            raise ValidationError(f"Payable {payable.bill_number} is already {payable.status} and cannot be re-verified.")

        # Check for material variance (variance > $100 or > 10% of total)
        total_amt = float(payable.total_amount) if payable.total_amount is not None else 0.0
        var_amt = abs(float(payable.variance_amount) if payable.variance_amount is not None else 0.0)
        is_material = var_amt > 100.0 or (total_amt > 0 and (var_amt / total_amt) > 0.10)

        now = datetime.now(UTC)

        if var_amt > 0:
            # Create / sync ShipmentException
            exc_severity = "CRITICAL" if var_amt > 500.0 else "WARNING"
            exc = ShipmentException(
                tenant_id=tenant_id,
                shipment_id=payable.shipment_id,
                exception_type="COST_VARIANCE",
                severity=exc_severity,
                domain="FINANCIAL",
                status="OPEN",
                description=f"Carrier/Vendor bill {payable.bill_number} has cost variance of {payable.variance_amount} {payable.currency_code}.",
                financial_impact_estimated=var_amt,
                opened_at=now,
            )
            self.session.add(exc)
            await self.session.flush()

        if is_material and not allow_material_variance:
            payable.verification_status = "VARIANCE_DETECTED"
            await self.session.flush()
            raise ValidationError(
                f"Payable {payable.bill_number} has a material variance of {payable.variance_amount} {payable.currency_code}. Review and explicit approval required."
            )

        payable.verification_status = "VERIFIED"
        payable.status = "VERIFIED"
        payable.verified_by = actor_id
        payable.verified_at = now
        if notes:
            payable.notes = (payable.notes or "") + f"\nVerification notes: {notes}"

        # Transition linked cost lines to VERIFIED
        lines_stmt = select(PayableLine).where(PayableLine.payable_id == payable_id)
        lines_res = await self.session.execute(lines_stmt)
        for pl in lines_res.scalars().all():
            pl.status = "VERIFIED"
            if pl.cost_line_id:
                cl_stmt = select(CostLine).where(CostLine.id == pl.cost_line_id)
                cl = (await self.session.execute(cl_stmt)).scalar_one_or_none()
                if cl and cl.status == "BILLED":
                    cl.status = "VERIFIED"

        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="payable",
                entity_id=str(payable.id),
                action="payable.verified",
                new_value={"status": "VERIFIED", "verification_status": "VERIFIED", "verified_at": now.isoformat()},
            )

        return await self.get_payable(payable.id, tenant_id)

    # -----------------------------------------------------------------------
    # 5.3.7 AP Approval Workflow
    # -----------------------------------------------------------------------
    async def approve_payable(
        self,
        *,
        payable_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Explicit AP approval for a verified carrier/vendor bill."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Payable).where(Payable.id == payable_id, Payable.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        payable = res.scalar_one_or_none()
        if not payable:
            raise NotFoundError(f"Payable {payable_id} not found.")

        if payable.approval_status == "APPROVED":
            raise ValidationError(f"Payable {payable.bill_number} is already approved.")

        if payable.verification_status != "VERIFIED":
            raise ValidationError(
                f"Payable {payable.bill_number} must be VERIFIED before approval. Current verification status: '{payable.verification_status}'."
            )

        now = datetime.now(UTC)
        today = date.today()
        payable.approval_status = "APPROVED"
        payable.status = "APPROVED"
        payable.approved_by = actor_id
        payable.approved_at = now
        if notes:
            payable.notes = (payable.notes or "") + f"\nApproval notes: {notes}"

        # 5.3.5 Transition linked CostLines to APPROVED
        lines_stmt = select(PayableLine).where(PayableLine.payable_id == payable_id)
        lines_res = await self.session.execute(lines_stmt)
        for pl in lines_res.scalars().all():
            if pl.cost_line_id:
                cl_stmt = select(CostLine).where(CostLine.id == pl.cost_line_id)
                cl = (await self.session.execute(cl_stmt)).scalar_one_or_none()
                if cl and cl.status == "VERIFIED":
                    cl.status = "APPROVED"

        # 5.3.9 Create Immutable Accounts Payable Financial Entry
        total_amt = float(payable.total_amount) if payable.total_amount is not None else 0.0
        fin_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=payable.shipment_id,
            entry_date=today,
            entry_type="ACCOUNTS_PAYABLE",
            debit_amount=0.0,
            credit_amount=total_amt,
            currency_code=payable.currency_code,
            description=f"AP Bill recognition {payable.bill_number} for Shipment",
            approved_by=actor_id,
            status="POSTED",
        )
        self.session.add(fin_entry)
        await self.session.flush()
        payable.financial_entry_id = fin_entry.id

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="payable",
                entity_id=str(payable.id),
                action="payable.approved",
                new_value={"status": "APPROVED", "approval_status": "APPROVED", "approved_at": now.isoformat()},
            )

        return await self.get_payable(payable.id, tenant_id)

    # -----------------------------------------------------------------------
    # 5.3.8 Payment Recording Workflow
    # -----------------------------------------------------------------------
    async def record_payment(
        self,
        *,
        payable_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        amount: float,
        payment_reference: str,
        payment_date: date | None = None,
        currency_code: str | None = None,
        payment_method: str = "WIRE_TRANSFER",
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Record partial or full payment against an approved payable bill."""
        if not self.session:
            raise ValidationError("Database session required")

        if amount <= 0:
            raise ValidationError("Payment amount must be positive.")

        stmt = select(Payable).where(Payable.id == payable_id, Payable.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        payable = res.scalar_one_or_none()
        if not payable:
            raise NotFoundError(f"Payable {payable_id} not found.")

        if payable.status not in {"APPROVED", "PARTIALLY_PAID"}:
            raise ValidationError(
                f"Cannot record payment for payable with status '{payable.status}'. Payable must be APPROVED."
            )

        total_amt = float(payable.total_amount) if payable.total_amount is not None else 0.0

        # Calculate existing payments to prevent overpayment
        existing_payments_stmt = select(func.coalesce(func.sum(PayablePayment.amount), 0.0)).where(
            PayablePayment.payable_id == payable_id,
            PayablePayment.tenant_id == tenant_id,
        )
        existing_paid = float((await self.session.execute(existing_payments_stmt)).scalar() or 0.0)
        remaining_balance = round(total_amt - existing_paid, 2)

        if remaining_balance <= 0:
            raise ValidationError(f"Payable {payable.bill_number} is already fully paid.")

        if amount > remaining_balance:
            raise ValidationError(
                f"Payment amount ({amount}) exceeds remaining balance ({remaining_balance}) on payable {payable.bill_number} (total: {total_amt}, previously paid: {existing_paid})."
            )

        pay_date = payment_date or date.today()
        curr = currency_code or payable.currency_code

        # 5.3.9 Create Immutable AP Payment Financial Entry
        fin_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=payable.shipment_id,
            entry_date=pay_date,
            entry_type="AP_PAYMENT",
            debit_amount=amount,
            credit_amount=0.0,
            currency_code=curr,
            description=f"AP Payment {payment_reference} for Bill {payable.bill_number}",
            approved_by=actor_id,
            status="POSTED",
        )
        self.session.add(fin_entry)
        await self.session.flush()

        payment = PayablePayment(
            tenant_id=tenant_id,
            payable_id=payable.id,
            payment_reference=payment_reference.strip(),
            payment_date=pay_date,
            amount=amount,
            currency_code=curr,
            payment_method=payment_method,
            financial_entry_id=fin_entry.id,
            recorded_by=actor_id,
            notes=notes,
        )
        self.session.add(payment)

        new_total_paid = round(existing_paid + amount, 2)
        payable.paid_amount = new_total_paid

        if new_total_paid >= total_amt:
            payable.status = "PAID"
            # Transition CostLines to PAID
            lines_stmt = select(PayableLine).where(PayableLine.payable_id == payable_id)
            lines_res = await self.session.execute(lines_stmt)
            for pl in lines_res.scalars().all():
                if pl.cost_line_id:
                    cl_stmt = select(CostLine).where(CostLine.id == pl.cost_line_id)
                    cl = (await self.session.execute(cl_stmt)).scalar_one_or_none()
                    if cl and cl.status == "APPROVED":
                        cl.status = "PAID"
        else:
            payable.status = "PARTIALLY_PAID"

        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="payable",
                entity_id=str(payable.id),
                action="payable.paid",
                new_value={
                    "payment_reference": payment_reference,
                    "amount": amount,
                    "paid_amount": new_total_paid,
                    "status": payable.status,
                },
            )

        return await self.get_payable(payable.id, tenant_id)
