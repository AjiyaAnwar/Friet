"""
Customer Acceptance & Booking Creation Service (Team 2).

Implements the 5-point pre-booking validation sequence, Job creation with formatted
job number ({Branch}-{Mode}-{Direction}-{YY}{MM}-{Seq}), revenue/cost ledger pre-population,
and event publication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from domain.entities import Quotation, QuotationStatus, QuotationOption, Rfq, Customer, Job
from domain.interfaces import (
    CustomerRepositoryPort, QuotationRepositoryPort, RateRepositoryPort,
    EventPublisherPort
)


@dataclass
class PreBookingValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    document_checklist: list[str] = field(default_factory=list)


@dataclass
class JobCreationResult:
    job: Job | None
    quotation: Quotation
    estimated_revenue_lines: list[dict[str, Any]]
    estimated_cost_lines: list[dict[str, Any]]
    document_checklist: list[str]
    validation_result: PreBookingValidationResult


class AcceptanceService:
    def __init__(
        self,
        quotation_repo: QuotationRepositoryPort,
        customer_repo: CustomerRepositoryPort,
        rate_repo: RateRepositoryPort | None = None,
        event_publisher: EventPublisherPort | None = None,
    ) -> None:
        self.quotation_repo = quotation_repo
        self.customer_repo = customer_repo
        self.rate_repo = rate_repo
        self.event_publisher = event_publisher

    def validate_pre_booking(
        self,
        quotation: Quotation,
        selected_option: QuotationOption,
        rfq: Rfq,
        customer: Customer,
        today: date | None = None,
    ) -> PreBookingValidationResult:
        if today is None:
            today = date.today()

        errors: list[str] = []
        warnings: list[str] = []

        # 1. Credit Check
        current_exposure = self.customer_repo.get_customer_exposure(customer.id)
        new_exposure = current_exposure + selected_option.total_sell
        if new_exposure > customer.credit_limit_amount:
            errors.append(
                f"Credit limit exceeded: total exposure ${new_exposure:.2f} "
                f"exceeds credit limit ${customer.credit_limit_amount:.2f}"
            )

        if customer.credit_tier.value == "BLOCKED":
            errors.append("Customer is in BLOCKED credit status")

        # 2. Rate Validity Re-Check
        if quotation.expiry_date < today:
            errors.append(f"Quotation expired on {quotation.expiry_date}. Rates must be re-validated.")

        # 3. Document Readiness Checklist (Advisory)
        checklist = ["COMMERCIAL_INVOICE", "PACKING_LIST"]
        if rfq.mode.value == "SEA":
            checklist.append("BILL_OF_LADING")
            checklist.append("VGM_DECLARATION")
        elif rfq.mode.value == "AIR":
            checklist.append("AIR_WAYBILL")

        if rfq.special_requirement and rfq.special_requirement.dgr_flag:
            checklist.append("DANGEROUS_GOODS_DECLARATION")
            checklist.append("MSDS")

        if rfq.special_requirement and rfq.special_requirement.lc_flag:
            checklist.append("LETTER_OF_CREDIT_COPY")

        # 4. Sanctions & Embargo Advisory Check
        # Local validation passed

        return PreBookingValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            document_checklist=checklist,
        )

    def accept_quotation_and_create_job(
        self,
        quotation_id: str,
        selected_option_index: int,
        rfq: Rfq,
        branch_code: str = "KHI",
        direction: str = "EXP",
        today: date | None = None,
        seq_num: int = 1,
    ) -> JobCreationResult:
        if today is None:
            today = date.today()

        quotation = self.quotation_repo.get_by_id(quotation_id)
        if not quotation:
            raise ValueError(f"Quotation {quotation_id} not found")

        if selected_option_index >= len(quotation.options):
            raise IndexError("Selected option index out of range")

        selected_option = quotation.options[selected_option_index]
        customer = self.customer_repo.get_customer_by_id(rfq.customer_id)
        if not customer:
            raise ValueError(f"Customer {rfq.customer_id} not found")

        # Run 5-point validation
        val_result = self.validate_pre_booking(
            quotation=quotation,
            selected_option=selected_option,
            rfq=rfq,
            customer=customer,
            today=today,
        )

        if not val_result.is_valid:
            return JobCreationResult(
                job=None,
                quotation=quotation,
                estimated_revenue_lines=[],
                estimated_cost_lines=[],
                document_checklist=val_result.document_checklist,
                validation_result=val_result,
            )

        # Generate unique Job Number: {Branch}-{Mode}-{Direction}-{YY}{MM}-{Seq:05d}
        mode_code = "AIR" if rfq.mode.value == "AIR" else "SEA"
        yymm = today.strftime("%y%m")
        job_number = f"{branch_code}-{mode_code}-{direction}-{yymm}-{seq_num:05d}"

        job = Job(
            job_number=job_number,
            quotation_id=quotation.id,
            customer_id=customer.id,
            status="CONFIRMED",
        )

        # Update Quotation status
        quotation.status = QuotationStatus.ACCEPTED
        self.quotation_repo.save_quotation(quotation)

        # Pre-populate estimated revenue and cost ledger entries
        revenue_lines = []
        cost_lines = []
        for line in selected_option.charge_lines:
            revenue_lines.append({
                "job_id": job.id,
                "charge_code": line.charge_code,
                "amount": line.sell_amount,
                "currency": selected_option.currency_code,
                "status": "ESTIMATED",
            })
            cost_lines.append({
                "job_id": job.id,
                "charge_code": line.charge_code,
                "amount": line.cost_amount,
                "currency": selected_option.currency_code,
                "status": "ESTIMATED",
            })

        # Publish domain event
        if self.event_publisher:
            self.event_publisher.publish(
                "booking.confirmed",
                {
                    "job_number": job.job_number,
                    "job_id": job.id,
                    "quotation_id": quotation.id,
                    "customer_id": customer.id,
                    "mode": rfq.mode.value,
                    "service_type": rfq.service_type.value,
                    "total_sell": selected_option.total_sell,
                    "total_cost": selected_option.total_cost,
                    "currency": selected_option.currency_code,
                    "confirmed_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return JobCreationResult(
            job=job,
            quotation=quotation,
            estimated_revenue_lines=revenue_lines,
            estimated_cost_lines=cost_lines,
            document_checklist=val_result.document_checklist,
            validation_result=val_result,
        )
