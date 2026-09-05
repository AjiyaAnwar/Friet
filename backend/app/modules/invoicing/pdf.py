"""Pure-Python Dependency-Free PDF Invoice Generator (Phase 5.2).

Renders a compliant %PDF-1.4 document containing complete header, customer,
shipment reference, line items, locked exchange rates, tax breakdowns, and payment terms.
"""

from __future__ import annotations

from typing import Any


class InvoicePDFGenerator:
    """Generates standard PDF documents from persisted invoice data."""

    @staticmethod
    def generate(invoice_data: dict[str, Any]) -> bytes:
        """Render a formatted %PDF-1.4 binary document from persisted invoice attributes."""
        lines: list[str] = []

        # 1. Header Information
        lines.append("FREIGHTCORE LOGISTICS - COMMERCIAL INVOICE")
        lines.append("======================================================================")
        lines.append(f"Invoice Number : {invoice_data.get('invoice_number', 'N/A')}")
        lines.append(f"Invoice Date   : {invoice_data.get('invoice_date', 'N/A')}")
        lines.append(f"Due Date       : {invoice_data.get('due_date') or 'Upon Receipt'}")
        lines.append(f"Status         : {invoice_data.get('status', 'DRAFT')}")
        lines.append(f"Currency       : {invoice_data.get('currency_code', 'USD')}")
        if float(invoice_data.get("exchange_rate_to_base", 1.0)) != 1.0:
            lines.append(f"Locked FX Rate : 1 {invoice_data.get('currency_code')} = {invoice_data.get('exchange_rate_to_base')} BASE")
        lines.append("----------------------------------------------------------------------")

        # 2. Customer & Reference Information
        lines.append(f"Customer       : {invoice_data.get('customer_name', 'Customer')}")
        if invoice_data.get("tax_registration"):
            lines.append(f"Tax Reg / VAT  : {invoice_data.get('tax_registration')}")
        lines.append(f"Job Reference  : {invoice_data.get('job_number') or 'N/A'}")
        lines.append(f"BL / AWB No    : {invoice_data.get('bl_awb_number') or 'N/A'}")
        lines.append(f"Customer PO    : {invoice_data.get('customer_po') or 'N/A'}")
        lines.append(f"Quotation Ref  : {invoice_data.get('quotation_number') or 'N/A'}")
        lines.append("======================================================================")

        # 3. Line Items Table Header
        lines.append(f"{'CHARGE':<15} {'DESC':<20} {'QTY':>5} {'RATE':>10} {'TAX':>8} {'TOTAL':>12}")
        lines.append("----------------------------------------------------------------------")

        # 4. Itemized Lines
        items = invoice_data.get("lines", [])
        for item in items:
            code = (item.get("charge_code") or "CHG")[:14]
            desc = (item.get("description") or code)[:19]
            qty = float(item.get("quantity", 1.0))
            rate = float(item.get("unit_rate") or item.get("amount", 0.0))
            tax = float(item.get("tax_amount", 0.0))
            total = float(item.get("total_amount") or item.get("amount", 0.0))
            lines.append(f"{code:<15} {desc:<20} {qty:>5.1f} {rate:>10.2f} {tax:>8.2f} {total:>12.2f}")

        # 5. Totals & Tax Summary
        lines.append("======================================================================")
        subtotal = float(invoice_data.get("subtotal_amount", 0.0))
        tax_total = float(invoice_data.get("tax_amount", 0.0))
        grand_total = float(invoice_data.get("total_amount", 0.0))
        tax_type = invoice_data.get("tax_type") or "Tax"
        tax_rate = float(invoice_data.get("tax_rate") or 0.0) * 100.0

        lines.append(f"{'Subtotal':>50} : {subtotal:>15.2f} {invoice_data.get('currency_code', 'USD')}")
        if tax_total > 0:
            lines.append(f"{f'{tax_type} ({tax_rate:.1f}%)':>50} : {tax_total:>15.2f} {invoice_data.get('currency_code', 'USD')}")
        lines.append(f"{'GRAND TOTAL':>50} : {grand_total:>15.2f} {invoice_data.get('currency_code', 'USD')}")
        lines.append("======================================================================")

        if invoice_data.get("payment_terms"):
            lines.append(f"Payment Terms: {invoice_data.get('payment_terms')}")
        if invoice_data.get("notes"):
            lines.append(f"Notes: {invoice_data.get('notes')}")

        # 6. Build PDF Stream
        # Escape parenthesis in text
        escaped_lines = [
            f"({line.replace('\\', '\\\\').replace('(', '[').replace(')', ']')}) Tj T*"
            for line in lines
        ]
        body = "\n".join(escaped_lines)
        stream = f"BT /F1 10 Tf 40 760 Td 14 TL\n{body}\nET".encode("latin-1", errors="replace")

        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        ]

        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("latin-1"))
            output.extend(obj)
            output.extend(b"\nendobj\n")

        xref = len(output)
        output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("latin-1"))
        output.extend(b"".join(f"{offset:010d} 00000 n \n".encode("latin-1") for offset in offsets[1:]))
        output.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("latin-1"))

        return bytes(output)
