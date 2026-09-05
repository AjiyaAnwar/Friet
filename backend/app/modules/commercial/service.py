"""Commercial business logic service integrating repository and calculations."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.commercial.calculations.air_freight import (
    Package,
    calculate_chargeable_weight,
)
from app.modules.commercial.calculations.container_utilization import (
    calculate_container_utilization,
)
from app.modules.commercial.calculations.lcl_revenue_tons import (
    calculate_lcl_revenue_tons,
)
from app.modules.commercial.rate_engine.expiry import (
    ExpiryCheckResult,
    check_rate_expiry,
)
from app.modules.commercial.rate_engine.models import Rate as DomainRate
from app.modules.commercial.repository import CommercialRepository


class CommercialService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        self.repo = CommercialRepository(session)

    # Master Data
    async def create_country(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.repo.create_country(data)

    async def get_country(self, country_id: str) -> dict[str, Any]:
        country = await self.repo.get_country(country_id)
        if not country:
            raise NotFoundError(f"Country with ID or code '{country_id}' not found")
        return country

    async def list_countries(self) -> list[dict[str, Any]]:
        return await self.repo.list_countries()

    async def credit_position(self, customer_id: str, tenant_id: uuid.UUID) -> dict[str, Any]:
        result = await self.repo.credit_position(customer_id, tenant_id)
        if not result:
            raise NotFoundError(f"Customer '{customer_id}' not found")
        return result

    async def create_location(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.repo.create_location(data)

    async def search_locations(
        self, query: str = "", location_type: str | None = None
    ) -> list[dict[str, Any]]:
        return await self.repo.search_locations(query=query, location_type=location_type)

    # Rate Engine
    async def create_rate(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        return await self.repo.create_rate(data, tenant_id)

    async def get_rate(self, rate_id: str) -> dict[str, Any]:
        rate = await self.repo.get_rate(rate_id)
        if not rate:
            raise NotFoundError(f"Rate with ID '{rate_id}' not found")
        return rate

    async def transition_rate(self, rate_id: str, to_status: str) -> dict[str, Any]:
        rate = await self.repo.transition_rate(rate_id, to_status)
        if not rate:
            raise NotFoundError(f"Rate with ID '{rate_id}' not found")
        return rate

    async def create_rate_version(
        self, rate_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        version = await self.repo.create_rate_version(rate_id, payload)
        if not version:
            raise NotFoundError(f"Rate with ID '{rate_id}' not found")
        return version

    async def get_expiry_report(self, today: date | None = None) -> dict[str, list[str]]:
        chk_date = today or date.today()
        raw_rates = await self.repo.list_all_rates()
        domain_rates = []
        for r in raw_rates:
            try:
                eff = (
                    date.fromisoformat(r["effective_date"])
                    if isinstance(r["effective_date"], str)
                    else r["effective_date"]
                )
                exp = (
                    date.fromisoformat(r["expiry_date"])
                    if isinstance(r["expiry_date"], str)
                    else r["expiry_date"]
                )
                domain_rates.append(
                    DomainRate(
                        id=r["id"],
                        rate_number=r["rate_number"],
                        rate_type=r["rate_type"],
                        rate_category=r["rate_category"],
                        carrier_vendor_id=r.get("carrier_vendor_id", ""),
                        service_name=r.get("service_name", ""),
                        origin_location_id=r.get("origin_location_id", ""),
                        destination_location_id=r.get("destination_location_id", ""),
                        via_routing=r.get("via_routing"),
                        commodity_id=r.get("commodity_id"),
                        customer_id=r.get("customer_id"),
                        effective_date=eff,
                        expiry_date=exp,
                        currency_code=r.get("currency_code", "USD"),
                        status=r.get("status", "ACTIVE"),
                    )
                )
            except Exception:
                continue

        result: ExpiryCheckResult = check_rate_expiry(domain_rates, chk_date)
        return {
            "warning": [r.id for r in result.warning],
            "escalation": [r.id for r in result.escalation],
            "newly_expired": [r.id for r in result.newly_expired],
        }

    # Calculations
    def calculate_air_weight(
        self, package_dicts: list[dict[str, Any]], divisor: int = 6000
    ) -> dict[str, Any]:
        packages = [
            Package(
                gross_weight_kg=p["gross_weight_kg"],
                length_cm=p["length_cm"],
                width_cm=p["width_cm"],
                height_cm=p["height_cm"],
                quantity=p.get("quantity", 1),
            )
            for p in package_dicts
        ]
        result = calculate_chargeable_weight(packages, divisor=divisor)
        return {
            "chargeable_weight_kg": result.chargeable_weight_kg,
            "gross_weight_kg": result.total_gross_weight_kg,
            "volumetric_weight_kg": result.total_volumetric_weight_kg,
            "basis": result.basis,
        }

    def calculate_container(
        self, cbm: float, gross_weight_kg: float, container_type: str
    ) -> dict[str, Any]:
        result = calculate_container_utilization(cbm, gross_weight_kg, container_type)
        return {
            "container_type": result.container_type,
            "volume_utilization_pct": result.volume_utilization_pct,
            "weight_utilization_pct": result.weight_utilization_pct,
            "effective_utilization_pct": result.effective_utilization_pct,
            "limiting_factor": result.limiting_factor,
            "warnings": result.warnings,
            "suggestions": result.suggestions,
        }

    def calculate_lcl(
        self, gross_weight_kg: float, cbm: float, carrier_minimum_rt: float = 1.0
    ) -> dict[str, Any]:
        result = calculate_lcl_revenue_tons(gross_weight_kg, cbm, carrier_minimum_rt)
        return {
            "gross_weight_kg": result.gross_weight_kg,
            "volume_cbm": result.volume_cbm,
            "weight_metric_tons": result.weight_metric_tons,
            "revenue_tons": result.revenue_tons,
            "billable_revenue_tons": result.billable_revenue_tons,
            "rating_basis": result.rating_basis,
            "is_minimum_applied": result.is_minimum_applied,
        }

    # RFQ (Phase 3)
    async def create_rfq(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        return await self.repo.create_rfq(data, tenant_id)

    async def get_rfq(self, rfq_id: str) -> dict[str, Any]:
        rfq = await self.repo.get_rfq(rfq_id)
        if not rfq:
            raise NotFoundError(f"RFQ with ID '{rfq_id}' not found")
        return rfq

    async def assign_rfq(self, rfq_id: str, user_id: str) -> dict[str, Any]:
        rfq = await self.repo.assign_rfq(rfq_id, user_id)
        if not rfq:
            raise NotFoundError(f"RFQ with ID '{rfq_id}' not found")
        return rfq

    # Quotation (Phase 3)
    async def create_quotation(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        return await self.repo.create_quotation(data, tenant_id)

    async def get_quotation(self, quotation_id: str) -> dict[str, Any]:
        quote = await self.repo.get_quotation(quotation_id)
        if not quote:
            raise NotFoundError(f"Quotation with ID '{quotation_id}' not found")
        return quote

    async def send_quotation(
        self, quotation_id: str, *, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ) -> dict[str, Any]:
        quote = await self.repo.send_quotation(quotation_id, tenant_id, actor_id)
        if not quote:
            raise NotFoundError(f"Quotation with ID '{quotation_id}' not found")
        return quote

    async def accept_quotation(
        self,
        quotation_id: str,
        customer_id: str | None = None,
        *,
        tenant_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        job = await self.repo.accept_quotation(
            quotation_id,
            customer_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
        )
        if not job:
            raise NotFoundError(f"Quotation with ID '{quotation_id}' not found")
        return job
