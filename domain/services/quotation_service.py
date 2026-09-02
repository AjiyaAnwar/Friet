"""
Commercial Quotation Service (Team 2).

Generates multi-option quotations, evaluates margin rules with lane/tier overrides,
handles quotation approval routing, revision chaining, and PDF generation context (SRS Section 3.5).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from domain.entities import (
    Quotation, QuotationOption, QuotationLine, QuotationStatus, QuotationApproval,
    Rfq, Customer, MarginRule, ChargeCategory, Route
)
from calculations.quotation_engine import evaluate_margin_rules, MarginEvaluationResult
from domain.interfaces import QuotationRepositoryPort, ExchangeRatePort, RulesEnginePort


class QuotationService:
    def __init__(
        self,
        quotation_repo: QuotationRepositoryPort,
        fx_service: ExchangeRatePort | None = None,
        rules_engine: RulesEnginePort | None = None,
    ) -> None:
        self.quotation_repo = quotation_repo
        self.fx_service = fx_service
        self.rules_engine = rules_engine

    def generate_quotation(
        self,
        rfq: Rfq,
        options: list[QuotationOption],
        validity_days: int = 14,
        margin_rules: list[MarginRule] | None = None,
        customer_tier: str | None = None,
        today: date | None = None,
    ) -> Quotation:
        if today is None:
            today = date.today()

        if not options:
            raise ValueError("At least one quotation option is required to generate a quotation")

        expiry_date = today + timedelta(days=validity_days)
        quote_num = f"QT-{rfq.rfq_number.replace('RFQ-', '')}-{today.strftime('%y%m%d')}"

        quotation = Quotation(
            quotation_number=quote_num,
            rfq_id=rfq.id,
            expiry_date=expiry_date,
            status=QuotationStatus.DRAFT,
            options=options,
        )

        # Evaluate margin rules on each option
        rules = margin_rules or []
        if not rules and self.rules_engine:
            rules = self.rules_engine.get_margin_rules(rfq.service_type.value)

        lane_code = f"{rfq.origin_location_id}-{rfq.destination_location_id}"
        service_type_str = rfq.service_type.value

        requires_margin_approval = False
        for opt in quotation.options:
            eval_res = evaluate_margin_rules(
                option=opt,
                service_type=service_type_str,
                rules=rules,
                customer_tier=customer_tier,
                lane_code=lane_code,
            )
            if not eval_res.passes:
                opt.is_below_margin = True
                requires_margin_approval = True

        # Generate required approvals
        approvals: list[QuotationApproval] = []
        if requires_margin_approval:
            approvals.append(
                QuotationApproval(
                    quotation_id=quotation.id,
                    approval_type="BELOW_MARGIN",
                    approver_role="PRICING_MANAGER",
                    status="PENDING",
                )
            )

        # High value check (e.g. total sell > $50,000)
        max_sell = max(opt.total_sell for opt in quotation.options)
        if max_sell > 50000:
            approvals.append(
                QuotationApproval(
                    quotation_id=quotation.id,
                    approval_type="HIGH_VALUE",
                    approver_role="FINANCE_CONTROLLER",
                    status="PENDING",
                )
            )

        # DGR compliance check
        if rfq.special_requirement and rfq.special_requirement.dgr_flag:
            approvals.append(
                QuotationApproval(
                    quotation_id=quotation.id,
                    approval_type="DGR_COMPLIANCE",
                    approver_role="COMPLIANCE_DGR",
                    status="PENDING",
                )
            )

        quotation.approvals = approvals
        if approvals:
            quotation.status = QuotationStatus.PENDING_APPROVAL
        else:
            quotation.status = QuotationStatus.APPROVED

        return self.quotation_repo.save_quotation(quotation)

    def revise_quotation(
        self,
        parent_quotation_id: str,
        new_options: list[QuotationOption],
        rfq: Rfq,
        margin_rules: list[MarginRule] | None = None,
        customer_tier: str | None = None,
        today: date | None = None,
    ) -> Quotation:
        parent = self.quotation_repo.get_by_id(parent_quotation_id)
        if not parent:
            raise ValueError(f"Parent quotation {parent_quotation_id} not found")

        # Mark parent as revised
        parent.status = QuotationStatus.REVISED
        self.quotation_repo.save_quotation(parent)

        # Create new revised quotation
        revised = self.generate_quotation(
            rfq=rfq,
            options=new_options,
            margin_rules=margin_rules,
            customer_tier=customer_tier,
            today=today,
        )
        revised.parent_quotation_id = parent.id
        return self.quotation_repo.save_quotation(revised)

    def send_to_customer(self, quotation_id: str) -> Quotation:
        quote = self.quotation_repo.get_by_id(quotation_id)
        if not quote:
            raise ValueError(f"Quotation {quotation_id} not found")

        pending_approvals = [a for a in quote.approvals if a.status != "APPROVED"]
        if pending_approvals:
            raise ValueError("Cannot send quotation to customer: pending approvals required")

        quote.status = QuotationStatus.SENT_TO_CUSTOMER
        quote.sent_at = datetime.now(timezone.utc)
        return self.quotation_repo.save_quotation(quote)

    def build_pdf_context(self, quotation: Quotation, rfq: Rfq, customer: Customer) -> dict:
        """
        Builds structured dictionary context for WeasyPrint PDF template rendering.
        """
        return {
            "company_name": "Inter-Fret Consolidators (Pvt.) Ltd.",
            "company_tagline": "Al-Rahim Group Freight Forwarding & Logistics",
            "quotation_number": quotation.quotation_number,
            "expiry_date": quotation.expiry_date.isoformat(),
            "customer_name": customer.name,
            "customer_code": customer.customer_code,
            "origin": rfq.origin_location_id,
            "destination": rfq.destination_location_id,
            "mode": rfq.mode.value,
            "service_type": rfq.service_type.value,
            "incoterm": rfq.incoterm_code,
            "options": [
                {
                    "label": opt.label,
                    "currency": opt.currency_code,
                    "total_cost": opt.total_cost,
                    "total_sell": opt.total_sell,
                    "gross_margin": opt.gross_margin,
                    "margin_pct": opt.margin_pct,
                    "charge_lines": [
                        {
                            "description": cl.description or cl.charge_code,
                            "category": cl.category.value,
                            "cost_amount": cl.cost_amount,
                            "sell_amount": cl.sell_amount,
                        }
                        for cl in opt.charge_lines
                    ],
                }
                for opt in quotation.options
            ],
            "terms_and_conditions": (
                "1. Rates subject to space and equipment availability.\n"
                "2. Surcharges subject to change as per carrier tariff at time of shipment.\n"
                "3. Standard trading terms of Inter-Fret Consolidators (Pvt.) Ltd. apply."
            ),
        }

    def render_html_quotation(self, quotation: Quotation, rfq: Rfq, customer: Customer) -> str:
        """
        Renders clean HTML quotation document for display or PDF conversion.
        """
        ctx = self.build_pdf_context(quotation, rfq, customer)

        options_html = ""
        for opt in ctx["options"]:
            lines_html = ""
            for line in opt["charge_lines"]:
                lines_html += f"""
                <tr>
                    <td>{line['description']}</td>
                    <td>{line['category']}</td>
                    <td style="text-align: right;">${line['sell_amount']:.2f}</td>
                </tr>
                """

            options_html += f"""
            <div style="border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; border-radius: 6px;">
                <h3>{opt['label']}</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="border-bottom: 2px solid #333;">
                            <th style="text-align: left;">Charge Description</th>
                            <th style="text-align: left;">Category</th>
                            <th style="text-align: right;">Sell Amount ({opt['currency']})</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lines_html}
                        <tr style="border-top: 2px solid #333; font-weight: bold;">
                            <td colspan="2">Total Selling Price:</td>
                            <td style="text-align: right;">${opt['total_sell']:.2f} {opt['currency']}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Quotation {ctx['quotation_number']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; color: #222; }}
        h1 {{ color: #0C447C; margin-bottom: 4px; }}
        .header {{ margin-bottom: 30px; border-bottom: 2px solid #0C447C; padding-bottom: 15px; }}
        .meta-table td {{ padding: 4px 10px; }}
        .terms {{ margin-top: 30px; font-size: 12px; color: #666; white-space: pre-line; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{ctx['company_name']}</h1>
        <p><em>{ctx['company_tagline']}</em></p>
    </div>
    <h2>COMMERCIAL QUOTATION</h2>
    <table class="meta-table">
        <tr><td><strong>Quotation No:</strong></td><td>{ctx['quotation_number']}</td><td><strong>Date:</strong></td><td>{datetime.now().strftime('%Y-%m-%d')}</td></tr>
        <tr><td><strong>Customer:</strong></td><td>{ctx['customer_name']} ({ctx['customer_code']})</td><td><strong>Valid Until:</strong></td><td>{ctx['expiry_date']}</td></tr>
        <tr><td><strong>Route:</strong></td><td>{ctx['origin']} &rarr; {ctx['destination']}</td><td><strong>Mode / Service:</strong></td><td>{ctx['mode']} / {ctx['service_type']}</td></tr>
        <tr><td><strong>Incoterm:</strong></td><td>{ctx['incoterm']}</td><td></td><td></td></tr>
    </table>
    <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
    {options_html}
    <div class="terms">
        <strong>Terms & Conditions:</strong><br>
        {ctx['terms_and_conditions']}
    </div>
</body>
</html>"""
        return html_doc
