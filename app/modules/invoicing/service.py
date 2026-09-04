"""Customer Invoicing Service (SRS Phase 5.2).

Manages invoice generation from Revenue Ledger, multi-currency conversion with locked rates,
tax calculation and snapshotting, threshold approval workflows, PDF rendering, transactional sending,
credit notes, debit notes, and financial integrity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.models.commercial import Customer, CustomerContact, Quotation
from app.db.models.domain import CreditNote, DebitNote, Invoice, InvoiceLine, RevenueLine, Shipment
from app.db.models.financial import FinancialEntry
from app.db.models.reference import ExchangeRate
from app.modules.audit.service import AuditService
from app.modules.events.service import OutboxService
from app.modules.invoicing.pdf import InvoicePDFGenerator
from app.modules.invoicing.tax import TaxService


class InvoiceService:
    """Core domain service for Customer Invoicing operations."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.audit = AuditService(session) if session else None
        self.outbox = OutboxService(session) if session else None

    # -----------------------------------------------------------------------
    # Helper: Verify tenant shipment
    # -----------------------------------------------------------------------
    async def _get_tenant_shipment(
        self, shipment_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Shipment:
        if not self.session:
            raise ValidationError("Database session required")
        stmt = select(Shipment).where(
            Shipment.id == shipment_id,
            Shipment.tenant_id == tenant_id,
        )
        res = await self.session.execute(stmt)
        shipment = res.scalar_one_or_none()
        if not shipment:
            raise NotFoundError(f"Shipment {shipment_id} not found or does not belong to tenant.")
        return shipment

    # -----------------------------------------------------------------------
    # Helper: Generate sequential references
    # -----------------------------------------------------------------------
    async def _get_next_sequence(self, model: type, tenant_id: uuid.UUID) -> int:
        if not self.session:
            return 1
        stmt = select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        count = res.scalar() or 0
        return count + 1

    # -----------------------------------------------------------------------
    # 5.2.1 Invoice Generation from Revenue Ledger
    # -----------------------------------------------------------------------
    async def generate_invoice(
        self,
        *,
        shipment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        currency_code: str | None = None,
        tax_jurisdiction: str | None = None,
        payment_terms: str | None = None,
        customer_po: str | None = None,
        notes: str | None = None,
        revenue_line_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        """Generate customer invoice from approved/estimated shipment revenue lines."""
        if not self.session:
            raise ValidationError("Database session required")

        shipment = await self._get_tenant_shipment(shipment_id, tenant_id)

        # 1. Fetch Customer
        cust_stmt = select(Customer).where(Customer.id == shipment.customer_id, Customer.tenant_id == tenant_id)
        cust_res = await self.session.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()
        if not customer:
            raise NotFoundError(f"Customer {shipment.customer_id} for shipment not found.")

        # 2. Fetch Eligible Revenue Lines (exclude already invoiced lines)
        rev_stmt = select(RevenueLine).where(RevenueLine.shipment_id == shipment_id)
        if revenue_line_ids:
            rev_stmt = rev_stmt.where(RevenueLine.id.in_(revenue_line_ids))
        else:
            rev_stmt = rev_stmt.where(RevenueLine.status.in_(["ESTIMATED", "QUOTED"]))

        rev_res = await self.session.execute(rev_stmt)
        revenue_lines = rev_res.scalars().all()

        if not revenue_lines:
            raise ValidationError("No eligible revenue lines available for invoicing on this shipment.")

        # Ensure no line is already INVOICED
        already_invoiced = [str(r.id) for r in revenue_lines if r.status == "INVOICED"]
        if already_invoiced:
            raise ValidationError(f"Revenue line(s) {', '.join(already_invoiced)} are already invoiced.")

        # 3. Resolve Target Currency
        target_curr = (currency_code or customer.credit_limit_currency or "USD").strip().upper()

        # 4. Determine & Lock Exchange Rate
        today = date.today()
        exchange_rate_to_base = 1.0
        exchange_rate_source = None
        if target_curr != "USD":
            xr_stmt = (
                select(ExchangeRate)
                .where(ExchangeRate.currency_code == target_curr, ExchangeRate.rate_date <= today)
                .order_by(ExchangeRate.rate_date.desc())
            )
            xr_res = await self.session.execute(xr_stmt)
            xr = xr_res.scalars().first()
            if xr:
                exchange_rate_to_base = float(xr.rate_to_base)
                exchange_rate_source = xr.source

        # 5. Evaluate Tax
        jurisdiction = tax_jurisdiction or "NONE"
        tax_eval = TaxService.evaluate(jurisdiction)

        # 6. Build Invoice Lines and Totals
        subtotal = 0.0
        tax_total = 0.0
        inv_lines_data: list[dict[str, Any]] = []

        for r in revenue_lines:
            src_amount = float(r.amount)
            src_curr = r.currency_code or "USD"

            # Convert to target currency if needed
            line_fx = 1.0
            if src_curr != target_curr and exchange_rate_to_base > 0:
                line_amount = round(src_amount * exchange_rate_to_base, 2)
                line_fx = exchange_rate_to_base
            else:
                line_amount = src_amount

            line_tax = tax_eval.compute_tax(line_amount)
            line_total = round(line_amount + line_tax, 2)

            subtotal += line_amount
            tax_total += line_tax

            inv_lines_data.append({
                "revenue_line_id": r.id,
                "charge_code": r.charge_code,
                "description": r.description or r.charge_code,
                "quantity": float(r.quantity) if r.quantity is not None else 1.0,
                "unit_rate": float(r.unit_rate) if r.unit_rate is not None else line_amount,
                "amount": line_amount,
                "source_amount": src_amount,
                "source_currency": src_curr,
                "exchange_rate": line_fx,
                "tax_rate": tax_eval.tax_rate,
                "tax_amount": line_tax,
                "total_amount": line_total,
            })

        grand_total = round(subtotal + tax_total, 2)

        # 7. Check Approval Threshold
        settings = get_settings()
        threshold = getattr(settings, "invoice_approval_threshold", 5000.0)

        now = datetime.now(UTC)
        if grand_total <= threshold:
            status = "APPROVED"
            approval_status = "APPROVED"
            approved_by = actor_id
            approved_at = now
        else:
            status = "PENDING_APPROVAL"
            approval_status = "PENDING"
            approved_by = None
            approved_at = None

        # 8. Generate Unique Invoice Number
        seq = await self._get_next_sequence(Invoice, tenant_id)
        invoice_number = f"INV-{today.year}-{seq:05d}"

        # 9. Create Invoice
        invoice = Invoice(
            tenant_id=tenant_id,
            customer_id=shipment.customer_id,
            shipment_id=shipment_id,
            invoice_number=invoice_number,
            invoice_date=today,
            currency_code=target_curr,
            exchange_rate_to_base=exchange_rate_to_base,
            exchange_rate_source=exchange_rate_source,
            subtotal_amount=subtotal,
            tax_amount=tax_total,
            total_amount=grand_total,
            amount=grand_total,  # legacy compatibility
            tax_jurisdiction=tax_eval.jurisdiction,
            tax_rate=tax_eval.tax_rate,
            tax_type=tax_eval.tax_type,
            job_number=str(shipment.job_id) if shipment.job_id else None,
            customer_po=customer_po,
            approval_status=approval_status,
            approved_by=approved_by,
            approved_at=approved_at,
            customer_email=None,
            payment_terms=payment_terms or (f"{customer.payment_terms_days} days" if customer.payment_terms_days else "Net 30"),
            notes=notes,
            status=status,
        )
        self.session.add(invoice)
        await self.session.flush()

        # 10. Persist Invoice Lines & Update Revenue Lines to INVOICED
        created_lines = []
        for l_data in inv_lines_data:
            inv_line = InvoiceLine(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                revenue_line_id=l_data["revenue_line_id"],
                charge_code=l_data["charge_code"],
                description=l_data["description"],
                quantity=l_data["quantity"],
                unit_rate=l_data["unit_rate"],
                amount=l_data["amount"],
                source_amount=l_data["source_amount"],
                source_currency=l_data["source_currency"],
                exchange_rate=l_data["exchange_rate"],
                tax_rate=l_data["tax_rate"],
                tax_amount=l_data["tax_amount"],
                total_amount=l_data["total_amount"],
            )
            self.session.add(inv_line)
            created_lines.append(inv_line)

        for r in revenue_lines:
            r.status = "INVOICED"

        await self.session.flush()

        # 11. Create Immutable Financial Ledger Entry for Accounts Receivable
        fin_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=shipment_id,
            entry_date=today,
            entry_type="INVOICE_RECEIVABLE",
            debit_amount=grand_total,
            credit_amount=0.0,
            currency_code=target_curr,
            description=f"Invoice {invoice.invoice_number} generated for shipment {shipment_id}",
            approved_by=approved_by,
            status="POSTED",
        )
        self.session.add(fin_entry)
        await self.session.flush()

        # 12. Audit Logging
        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="invoice",
                entity_id=str(invoice.id),
                action="invoice.created",
                new_value={
                    "invoice_number": invoice.invoice_number,
                    "total_amount": grand_total,
                    "currency": target_curr,
                    "status": status,
                    "lines_count": len(created_lines),
                },
            )

        return await self.get_invoice(invoice.id, tenant_id)

    # -----------------------------------------------------------------------
    # 5.2.2 Invoice Retrieval & Listing
    # -----------------------------------------------------------------------
    async def get_invoice(self, invoice_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        """Get full details of an invoice including locked lines and tax snapshots."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")

        # Customer name & tax info
        cust_stmt = select(Customer).where(Customer.id == invoice.customer_id)
        cust_res = await self.session.execute(cust_stmt)
        customer = cust_res.scalar_one_or_none()

        # Lines
        lines_stmt = (
            select(InvoiceLine)
            .where(InvoiceLine.invoice_id == invoice_id)
            .order_by(InvoiceLine.created_at.asc())
        )
        lines_res = await self.session.execute(lines_stmt)
        lines = lines_res.scalars().all()

        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "customer_id": str(invoice.customer_id),
            "customer_name": customer.name if customer else "Customer",
            "tax_registration": customer.tax_registration_encrypted if customer else None,
            "shipment_id": str(invoice.shipment_id),
            "job_number": invoice.job_number,
            "bl_awb_number": invoice.bl_awb_number,
            "customer_po": invoice.customer_po,
            "quotation_id": str(invoice.quotation_id) if invoice.quotation_id else None,
            "currency_code": invoice.currency_code,
            "exchange_rate_to_base": float(invoice.exchange_rate_to_base) if invoice.exchange_rate_to_base is not None else 1.0,
            "subtotal_amount": float(invoice.subtotal_amount) if invoice.subtotal_amount is not None else 0.0,
            "tax_amount": float(invoice.tax_amount) if invoice.tax_amount is not None else 0.0,
            "total_amount": float(invoice.total_amount) if invoice.total_amount is not None else 0.0,
            "tax_jurisdiction": invoice.tax_jurisdiction,
            "tax_rate": float(invoice.tax_rate) if invoice.tax_rate is not None else 0.0,
            "tax_type": invoice.tax_type,
            "approval_status": invoice.approval_status,
            "approved_by": str(invoice.approved_by) if invoice.approved_by else None,
            "approved_at": invoice.approved_at.isoformat() if invoice.approved_at else None,
            "sent_at": invoice.sent_at.isoformat() if invoice.sent_at else None,
            "sent_by": str(invoice.sent_by) if invoice.sent_by else None,
            "payment_terms": invoice.payment_terms,
            "notes": invoice.notes,
            "status": invoice.status,
            "lines": [
                {
                    "id": str(l.id),
                    "revenue_line_id": str(l.revenue_line_id) if l.revenue_line_id else None,
                    "charge_code": l.charge_code,
                    "description": l.description,
                    "quantity": float(l.quantity) if l.quantity is not None else 1.0,
                    "unit_rate": float(l.unit_rate) if l.unit_rate is not None else None,
                    "amount": float(l.amount) if l.amount is not None else 0.0,
                    "source_amount": float(l.source_amount) if l.source_amount is not None else 0.0,
                    "source_currency": l.source_currency,
                    "exchange_rate": float(l.exchange_rate) if l.exchange_rate is not None else 1.0,
                    "tax_rate": float(l.tax_rate) if l.tax_rate is not None else 0.0,
                    "tax_amount": float(l.tax_amount) if l.tax_amount is not None else 0.0,
                    "total_amount": float(l.total_amount) if l.total_amount is not None else 0.0,
                }
                for l in lines
            ],
        }

    async def list_invoices(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        shipment_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List tenant invoices with optional filtering."""
        if not self.session:
            return []

        stmt = select(Invoice).where(Invoice.tenant_id == tenant_id)
        if customer_id:
            stmt = stmt.where(Invoice.customer_id == customer_id)
        if shipment_id:
            stmt = stmt.where(Invoice.shipment_id == shipment_id)
        if status:
            stmt = stmt.where(Invoice.status == status.strip().upper())

        stmt = stmt.order_by(Invoice.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        invoices = res.scalars().all()

        results = []
        for inv in invoices:
            results.append({
                "id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "customer_id": str(inv.customer_id),
                "shipment_id": str(inv.shipment_id),
                "currency_code": inv.currency_code,
                "total_amount": float(inv.total_amount) if inv.total_amount is not None else 0.0,
                "approval_status": inv.approval_status,
                "status": inv.status,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            })
        return results

    # -----------------------------------------------------------------------
    # 5.2.3 Invoice Approval Workflow
    # -----------------------------------------------------------------------
    async def approve_invoice(
        self,
        *,
        invoice_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Explicitly approve an invoice that required approval."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")

        if invoice.status == "APPROVED":
            return await self.get_invoice(invoice_id, tenant_id)

        if invoice.status != "PENDING_APPROVAL":
            raise ValidationError(f"Cannot approve invoice in status '{invoice.status}'.")

        invoice.status = "APPROVED"
        invoice.approval_status = "APPROVED"
        invoice.approved_by = actor_id
        invoice.approved_at = datetime.now(UTC)
        if notes:
            invoice.notes = f"{invoice.notes}\nApproval note: {notes}" if invoice.notes else f"Approval note: {notes}"

        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="invoice",
                entity_id=str(invoice.id),
                action="invoice.approved",
                new_value={"status": "APPROVED", "approved_by": str(actor_id)},
            )

        return await self.get_invoice(invoice_id, tenant_id)

    # -----------------------------------------------------------------------
    # 5.2.4 PDF Generation
    # -----------------------------------------------------------------------
    async def generate_invoice_pdf(self, invoice_id: uuid.UUID, tenant_id: uuid.UUID) -> bytes:
        """Render a branded PDF invoice strictly from persisted data."""
        data = await self.get_invoice(invoice_id, tenant_id)
        return InvoicePDFGenerator.generate(data)

    # -----------------------------------------------------------------------
    # 5.2.5 Send Invoice to Customer
    # -----------------------------------------------------------------------
    async def send_invoice(
        self,
        *,
        invoice_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        recipient_email: str | None = None,
    ) -> dict[str, Any]:
        """Send approved invoice to customer via outbox event with PDF attachment."""
        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")

        # Strict Precondition: Must be approved before sending
        if invoice.status not in {"APPROVED", "SENT"}:
            raise ValidationError(f"Invoice must be APPROVED before sending. Current status: '{invoice.status}'.")

        # Resolve email
        email = recipient_email
        if not email:
            contact_stmt = select(CustomerContact).where(CustomerContact.customer_id == invoice.customer_id)
            contact_res = await self.session.execute(contact_stmt)
            contact = contact_res.scalars().first()
            email = invoice.customer_email or (contact.email_encrypted if contact else None)

        if not email:
            raise ValidationError("Recipient email is required to send invoice.")

        now = datetime.now(UTC)
        invoice.status = "SENT"
        invoice.sent_at = now
        invoice.sent_by = actor_id
        invoice.customer_email = email
        await self.session.flush()

        # Generate PDF for attachment metadata
        inv_data = await self.get_invoice(invoice_id, tenant_id)

        # Transactional Outbox Event
        if self.outbox:
            await self.outbox.enqueue(
                event_type="invoice.sent",
                tenant_id=tenant_id,
                aggregate_type="invoice",
                aggregate_id=invoice.id,
                payload={
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "recipient_email": email,
                    "total_amount": float(invoice.total_amount) if invoice.total_amount is not None else 0.0,
                    "currency": invoice.currency_code,
                    "customer_id": str(invoice.customer_id),
                    "sent_at": now.isoformat(),
                },
            )

        # Audit Log
        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="invoice",
                entity_id=str(invoice.id),
                action="invoice.sent",
                new_value={"status": "SENT", "recipient_email": email, "sent_at": now.isoformat()},
            )

        return {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "status": "SENT",
            "recipient_email": email,
            "sent_at": now.isoformat(),
        }

    # -----------------------------------------------------------------------
    # 5.2.6 Credit Notes
    # -----------------------------------------------------------------------
    async def create_credit_note(
        self,
        *,
        invoice_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        amount: float,
        reason: str,
        currency_code: str | None = None,
    ) -> dict[str, Any]:
        """Issue full or partial credit note linked to original invoice."""
        if amount <= 0:
            raise ValidationError("Credit note amount must be positive.")
        if not reason or len(reason.strip()) < 3:
            raise ValidationError("Credit note reason is required (minimum 3 characters).")

        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")

        inv_total = float(invoice.total_amount) if invoice.total_amount is not None else 0.0

        # Calculate existing credits issued for this invoice
        cn_stmt = (
            select(func.coalesce(func.sum(CreditNote.amount), 0.0))
            .where(
                CreditNote.invoice_id == invoice_id,
                CreditNote.tenant_id == tenant_id,
                CreditNote.status != "CANCELLED",
            )
        )
        existing_credited = float((await self.session.execute(cn_stmt)).scalar() or 0.0)
        remaining_creditable = round(inv_total - existing_credited, 2)

        if remaining_creditable <= 0:
            raise ValidationError(f"Invoice {invoice.invoice_number} has already been fully credited.")

        if amount > remaining_creditable:
            raise ValidationError(
                f"Credit note amount ({amount}) exceeds remaining creditable amount ({remaining_creditable}) on invoice {invoice.invoice_number} (total: {inv_total}, previously credited: {existing_credited})."
            )

        if round(existing_credited + amount, 2) >= inv_total:
            invoice.status = "CREDITED"

        today = date.today()
        seq = await self._get_next_sequence(CreditNote, tenant_id)
        cn_number = f"CN-{today.year}-{seq:05d}"
        curr = currency_code or invoice.currency_code

        # Create Offsetting AR Financial Entry
        fin_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=invoice.shipment_id,
            entry_date=today,
            entry_type="CREDIT_NOTE",
            debit_amount=0.0,
            credit_amount=amount,
            currency_code=curr,
            description=f"Credit Note {cn_number} for Invoice {invoice.invoice_number}: {reason}",
            approved_by=actor_id,
            status="POSTED",
        )
        self.session.add(fin_entry)
        await self.session.flush()

        credit_note = CreditNote(
            tenant_id=tenant_id,
            credit_note_number=cn_number,
            invoice_id=invoice_id,
            customer_id=invoice.customer_id,
            amount=amount,
            tax_amount=0.0,
            total_amount=amount,
            currency_code=curr,
            reason=reason.strip(),
            credit_note_date=today,
            status="ISSUED",
            created_by=actor_id,
            financial_entry_id=fin_entry.id,
        )
        self.session.add(credit_note)
        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="credit_note",
                entity_id=str(credit_note.id),
                action="credit_note.issued",
                new_value={
                    "credit_note_number": cn_number,
                    "invoice_id": str(invoice_id),
                    "amount": amount,
                    "reason": reason,
                },
            )

        return {
            "id": str(credit_note.id),
            "credit_note_number": credit_note.credit_note_number,
            "invoice_id": str(invoice_id),
            "invoice_number": invoice.invoice_number,
            "amount": float(credit_note.amount),
            "currency_code": credit_note.currency_code,
            "reason": credit_note.reason,
            "status": credit_note.status,
            "credit_note_date": credit_note.credit_note_date.isoformat(),
        }

    # -----------------------------------------------------------------------
    # 5.2.7 Debit Notes
    # -----------------------------------------------------------------------
    async def create_debit_note(
        self,
        *,
        invoice_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        charge_code: str,
        amount: float,
        reason: str,
        currency_code: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Issue debit note for additional charge linked to original invoice."""
        if amount <= 0:
            raise ValidationError("Debit note amount must be positive.")
        if not charge_code or not charge_code.strip():
            raise ValidationError("Charge code is required.")
        if not reason or len(reason.strip()) < 3:
            raise ValidationError("Debit note reason is required (minimum 3 characters).")

        if not self.session:
            raise ValidationError("Database session required")

        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
        res = await self.session.execute(stmt)
        invoice = res.scalar_one_or_none()
        if not invoice:
            raise NotFoundError(f"Invoice {invoice_id} not found.")

        today = date.today()
        seq = await self._get_next_sequence(DebitNote, tenant_id)
        dn_number = f"DN-{today.year}-{seq:05d}"
        curr = currency_code or invoice.currency_code

        # Create AR Financial Entry for Debit Note
        fin_entry = FinancialEntry(
            tenant_id=tenant_id,
            shipment_id=invoice.shipment_id,
            entry_date=today,
            entry_type="DEBIT_NOTE",
            debit_amount=amount,
            credit_amount=0.0,
            currency_code=curr,
            description=f"Debit Note {dn_number} for Invoice {invoice.invoice_number} ({charge_code}): {reason}",
            approved_by=actor_id,
            status="POSTED",
        )
        self.session.add(fin_entry)
        await self.session.flush()

        debit_note = DebitNote(
            tenant_id=tenant_id,
            debit_note_number=dn_number,
            invoice_id=invoice_id,
            customer_id=invoice.customer_id,
            amount=amount,
            tax_amount=0.0,
            total_amount=amount,
            currency_code=curr,
            charge_code=charge_code.strip().upper(),
            description=description or charge_code.strip().upper(),
            reason=reason.strip(),
            debit_note_date=today,
            status="ISSUED",
            created_by=actor_id,
            financial_entry_id=fin_entry.id,
        )
        self.session.add(debit_note)
        await self.session.flush()

        if self.audit:
            await self.audit.record(
                tenant_id=tenant_id,
                user_id=actor_id,
                branch_id=None,
                entity_type="debit_note",
                entity_id=str(debit_note.id),
                action="debit_note.issued",
                new_value={
                    "debit_note_number": dn_number,
                    "invoice_id": str(invoice_id),
                    "charge_code": debit_note.charge_code,
                    "amount": amount,
                    "reason": reason,
                },
            )

        return {
            "id": str(debit_note.id),
            "debit_note_number": debit_note.debit_note_number,
            "invoice_id": str(invoice_id),
            "invoice_number": invoice.invoice_number,
            "charge_code": debit_note.charge_code,
            "amount": float(debit_note.amount),
            "currency_code": debit_note.currency_code,
            "reason": debit_note.reason,
            "status": debit_note.status,
            "debit_note_date": debit_note.debit_note_date.isoformat(),
        }
