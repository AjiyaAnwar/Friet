"""Commercial repository layer integrating with Team 1 SQLAlchemy ORM models."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models.commercial import (
    Job as DBJob,
    Quotation as DBQuotation,
    QuotationLine as DBQuotationLine,
    QuotationOption as DBQuotationOption,
    Rate as DBRate,
    RateLine as DBRateLine,
    RateSurcharge as DBRateSurcharge,
    RateVersion as DBRateVersion,
    RFQ as DBRFQ,
    RFQCargoLine as DBRFQCargoLine,
    RFQContainerRequirement as DBRFQContainerRequirement,
    RFQSpecialRequirement as DBRFQSpecialRequirement,
)
from app.db.models.reference import (
    Carrier as DBCarrier,
    ContainerType as DBContainerType,
    Country as DBCountry,
    Currency as DBCurrency,
    ExchangeRate as DBExchangeRate,
    Incoterm as DBIncoterm,
    Location as DBLocation,
)

# In-memory stores used ONLY when session is None (isolated unit-test doubles)
_IN_MEMORY_COUNTRIES: dict[str, dict[str, Any]] = {}
_IN_MEMORY_LOCATIONS: dict[str, dict[str, Any]] = {}
_IN_MEMORY_RATES: dict[str, dict[str, Any]] = {}
_IN_MEMORY_RATE_VERSIONS: dict[str, list[dict[str, Any]]] = {}
_IN_MEMORY_RFQS: dict[str, dict[str, Any]] = {}
_IN_MEMORY_QUOTATIONS: dict[str, dict[str, Any]] = {}
_IN_MEMORY_JOBS: dict[str, dict[str, Any]] = {}


def _parse_uuid(val: Any) -> uuid.UUID | None:
    if not val:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        return None


class CommercialRepository:
    """Repository handling persistence for Master Data, Rates, RFQs, and Quotations.

    When session is provided (production), all queries execute against PostgreSQL.
    When session is None, operates as an in-memory double for isolated unit tests.
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    # =========================================================================
    # Countries
    # =========================================================================
    async def create_country(self, data: dict[str, Any]) -> dict[str, Any]:
        iso_code = data["iso_code"].upper()
        if self.session is None:
            c_id = str(uuid.uuid4())
            res = {
                "id": c_id,
                "iso_code": iso_code,
                "name": data["name"],
                "region": data.get("region", ""),
                "trade_zone": data.get("trade_zone", ""),
                "is_sanctioned": data.get("is_sanctioned", False),
                "requires_permit": data.get("requires_permit", False),
            }
            _IN_MEMORY_COUNTRIES[c_id] = res
            _IN_MEMORY_COUNTRIES[iso_code] = res
            return res

        country = DBCountry(
            iso_code=iso_code,
            name=data["name"],
            region=data.get("region"),
            trade_zone=data.get("trade_zone"),
            is_sanctioned=data.get("is_sanctioned", False),
            requires_permit=data.get("requires_permit", False),
        )
        self.session.add(country)
        await self.session.flush()
        return {
            "id": str(country.id),
            "iso_code": country.iso_code,
            "name": country.name,
            "region": country.region or "",
            "trade_zone": country.trade_zone or "",
            "is_sanctioned": country.is_sanctioned,
            "requires_permit": country.requires_permit,
        }

    async def get_country(self, country_id: str) -> dict[str, Any] | None:
        if self.session is None:
            return _IN_MEMORY_COUNTRIES.get(country_id) or _IN_MEMORY_COUNTRIES.get(country_id.upper())

        u_id = _parse_uuid(country_id)
        stmt = select(DBCountry).where(
            or_(DBCountry.id == u_id, DBCountry.iso_code == country_id.upper())
            if u_id
            else DBCountry.iso_code == country_id.upper()
        )
        result = await self.session.execute(stmt)
        country = result.scalar_one_or_none()
        if not country:
            return None
        return {
            "id": str(country.id),
            "iso_code": country.iso_code,
            "name": country.name,
            "region": country.region or "",
            "trade_zone": country.trade_zone or "",
            "is_sanctioned": country.is_sanctioned,
            "requires_permit": country.requires_permit,
        }

    # =========================================================================
    # Locations
    # =========================================================================
    async def create_location(self, data: dict[str, Any]) -> dict[str, Any]:
        c_id_raw = data.get("country_id")
        if self.session is None:
            loc_id = str(uuid.uuid4())
            res = {
                "id": loc_id,
                "un_locode": data.get("un_locode"),
                "iata_code": data.get("iata_code"),
                "name": data["name"],
                "country_id": str(c_id_raw),
                "city": data.get("city", ""),
                "type": data.get("type", "PORT"),
                "timezone": data.get("timezone", "UTC"),
                "is_active": data.get("is_active", True),
            }
            _IN_MEMORY_LOCATIONS[loc_id] = res
            return res

        country_uuid = _parse_uuid(c_id_raw)
        if not country_uuid and c_id_raw:
            c_stmt = select(DBCountry.id).where(DBCountry.iso_code == str(c_id_raw).upper())
            c_res = await self.session.execute(c_stmt)
            country_uuid = c_res.scalar_one_or_none()

        if not country_uuid:
            raise ValidationError(
                f"Valid country_id or ISO code is required for location (got '{c_id_raw}')"
            )

        loc = DBLocation(
            un_locode=data.get("un_locode"),
            iata_code=data.get("iata_code"),
            name=data["name"],
            country_id=country_uuid,
            city=data.get("city"),
            type=data.get("type", "PORT"),
            timezone=data.get("timezone", "UTC"),
            is_active=data.get("is_active", True),
        )
        self.session.add(loc)
        await self.session.flush()
        return {
            "id": str(loc.id),
            "un_locode": loc.un_locode,
            "iata_code": loc.iata_code,
            "name": loc.name,
            "country_id": str(loc.country_id),
            "city": loc.city or "",
            "type": loc.type,
            "timezone": loc.timezone or "UTC",
            "is_active": loc.is_active,
        }

    async def search_locations(
        self, query: str = "", location_type: str | None = None
    ) -> list[dict[str, Any]]:
        q_lower = query.strip().lower()
        if self.session is None:
            res = []
            for loc in _IN_MEMORY_LOCATIONS.values():
                if location_type and loc["type"] != location_type:
                    continue
                if not q_lower or (
                    q_lower in loc["name"].lower()
                    or q_lower in loc["city"].lower()
                    or q_lower in (loc.get("un_locode") or "").lower()
                    or q_lower in (loc.get("iata_code") or "").lower()
                ):
                    res.append(loc)
            return res

        stmt = select(DBLocation).where(DBLocation.is_active.is_(True))
        if location_type:
            stmt = stmt.where(DBLocation.type == location_type)
        result = await self.session.execute(stmt)
        db_locs = result.scalars().all()
        results = []
        for loc in db_locs:
            if not q_lower or (
                q_lower in (loc.name or "").lower()
                or q_lower in (loc.city or "").lower()
                or q_lower in (loc.un_locode or "").lower()
                or q_lower in (loc.iata_code or "").lower()
            ):
                results.append(
                    {
                        "id": str(loc.id),
                        "un_locode": loc.un_locode,
                        "iata_code": loc.iata_code,
                        "name": loc.name,
                        "country_id": str(loc.country_id),
                        "city": loc.city or "",
                        "type": loc.type,
                        "timezone": loc.timezone or "UTC",
                        "is_active": loc.is_active,
                    }
                )
        return results

    # =========================================================================
    # Rates & Versions
    # =========================================================================
    async def create_rate(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        eff_date = (
            date.fromisoformat(data["effective_date"])
            if isinstance(data["effective_date"], str)
            else data["effective_date"]
        )
        exp_date = (
            date.fromisoformat(data["expiry_date"])
            if isinstance(data["expiry_date"], str)
            else data["expiry_date"]
        )

        if self.session is None:
            rate_id = str(uuid.uuid4())
            res = {
                "id": rate_id,
                "rate_number": data["rate_number"],
                "rate_type": data["rate_type"],
                "rate_category": data["rate_category"],
                "carrier_vendor_id": data.get("carrier_vendor_id", ""),
                "service_name": data.get("service_name", ""),
                "origin_location_id": data.get("origin_location_id", ""),
                "destination_location_id": data.get("destination_location_id", ""),
                "effective_date": str(eff_date),
                "expiry_date": str(exp_date),
                "currency_code": data.get("currency_code", "USD"),
                "status": "DRAFT",
            }
            _IN_MEMORY_RATES[rate_id] = res
            return res

        if tenant_id is None:
            raise ValidationError("Tenant ID is required to create a rate")

        rate = DBRate(
            tenant_id=tenant_id,
            rate_number=data["rate_number"],
            rate_type=data["rate_type"],
            rate_category=data["rate_category"],
            carrier_id=_parse_uuid(data.get("carrier_vendor_id")),
            service_name=data.get("service_name"),
            origin_location_id=_parse_uuid(data.get("origin_location_id")),
            destination_location_id=_parse_uuid(data.get("destination_location_id")),
            via_routing=data.get("via_routing"),
            commodity_id=_parse_uuid(data.get("commodity_id")),
            customer_id=_parse_uuid(data.get("customer_id")),
            effective_date=eff_date,
            expiry_date=exp_date,
            currency_code=data.get("currency_code", "USD"),
            status="DRAFT",
        )
        self.session.add(rate)
        await self.session.flush()
        return {
            "id": str(rate.id),
            "rate_number": rate.rate_number,
            "rate_type": rate.rate_type,
            "rate_category": rate.rate_category,
            "carrier_vendor_id": data.get("carrier_vendor_id", ""),
            "service_name": rate.service_name or "",
            "origin_location_id": data.get("origin_location_id", ""),
            "destination_location_id": data.get("destination_location_id", ""),
            "effective_date": str(rate.effective_date),
            "expiry_date": str(rate.expiry_date),
            "currency_code": rate.currency_code,
            "status": rate.status,
        }

    async def get_rate(self, rate_id: str) -> dict[str, Any] | None:
        if self.session is None:
            return _IN_MEMORY_RATES.get(rate_id)

        u_id = _parse_uuid(rate_id)
        if not u_id:
            return None
        stmt = select(DBRate).where(DBRate.id == u_id)
        result = await self.session.execute(stmt)
        rate = result.scalar_one_or_none()
        if not rate:
            return None
        return {
            "id": str(rate.id),
            "rate_number": rate.rate_number,
            "rate_type": rate.rate_type,
            "rate_category": rate.rate_category,
            "carrier_vendor_id": str(rate.carrier_id) if rate.carrier_id else "",
            "service_name": rate.service_name or "",
            "origin_location_id": str(rate.origin_location_id) if rate.origin_location_id else "",
            "destination_location_id": str(rate.destination_location_id) if rate.destination_location_id else "",
            "effective_date": str(rate.effective_date),
            "expiry_date": str(rate.expiry_date),
            "currency_code": rate.currency_code,
            "status": rate.status,
        }

    async def list_all_rates(self) -> list[dict[str, Any]]:
        if self.session is None:
            return list(_IN_MEMORY_RATES.values())

        stmt = select(DBRate)
        result = await self.session.execute(stmt)
        rates = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "rate_number": r.rate_number,
                "rate_type": r.rate_type,
                "rate_category": r.rate_category,
                "carrier_vendor_id": str(r.carrier_id) if r.carrier_id else "",
                "service_name": r.service_name or "",
                "origin_location_id": str(r.origin_location_id) if r.origin_location_id else "",
                "destination_location_id": str(r.destination_location_id) if r.destination_location_id else "",
                "effective_date": str(r.effective_date),
                "expiry_date": str(r.expiry_date),
                "currency_code": r.currency_code,
                "status": r.status,
            }
            for r in rates
        ]

    async def create_rate_version(
        self, rate_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        if self.session is None:
            rate = await self.get_rate(rate_id)
            if not rate:
                return None
            current_versions = _IN_MEMORY_RATE_VERSIONS.get(rate_id, [])
            version_num = len(current_versions) + 1
            v_id = str(uuid.uuid4())
            res = {
                "id": v_id,
                "rate_id": rate_id,
                "version_number": version_num,
                "modified_by": payload.get("modified_by", ""),
                "reason": payload.get("reason", ""),
                "approval_status": "DRAFT",
            }
            current_versions.append(res)
            _IN_MEMORY_RATE_VERSIONS[rate_id] = current_versions
            return res

        r_uuid = _parse_uuid(rate_id)
        if not r_uuid:
            return None

        # Lock parent rate row to prevent concurrent version collisions
        rate_stmt = select(DBRate).where(DBRate.id == r_uuid).with_for_update()
        rate_res = await self.session.execute(rate_stmt)
        rate = rate_res.scalar_one_or_none()
        if not rate:
            return None

        # Concurrency-safe version number generation
        ver_stmt = select(func.coalesce(func.max(DBRateVersion.version_number), 0)).where(
            DBRateVersion.rate_id == r_uuid
        )
        max_ver = (await self.session.execute(ver_stmt)).scalar_one()
        version_num = max_ver + 1

        mod_by = _parse_uuid(payload.get("modified_by"))
        version = DBRateVersion(
            rate_id=r_uuid,
            version_number=version_num,
            modified_by=mod_by,
            modified_date=datetime.now(UTC),
            reason=payload.get("reason", ""),
            approval_status="DRAFT",
        )
        self.session.add(version)
        await self.session.flush()

        for line in payload.get("lines", []):
            db_line = DBRateLine(
                rate_version_id=version.id,
                charge_code=line["charge_code"],
                rate_basis=line["rate_basis"],
                weight_break_from=line.get("weight_break_from"),
                weight_break_to=line.get("weight_break_to"),
                container_type_code=line.get("container_type_code"),
                amount=line["amount"],
            )
            self.session.add(db_line)
        await self.session.flush()

        return {
            "id": str(version.id),
            "rate_id": rate_id,
            "version_number": version.version_number,
            "modified_by": payload.get("modified_by", ""),
            "reason": version.reason or "",
            "approval_status": version.approval_status,
        }

    # =========================================================================
    # RFQ (Phase 3)
    # =========================================================================
    async def create_rfq(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        rfq_number = data.get("rfq_number") or f"RFQ-{uuid.uuid4().hex[:8].upper()}"
        if self.session is None:
            rfq_id = str(uuid.uuid4())
            res = {
                "id": rfq_id,
                "rfq_number": rfq_number,
                "customer_id": str(data["customer_id"]),
                "mode": data.get("mode", "AIR"),
                "status": "SUBMITTED",
            }
            _IN_MEMORY_RFQS[rfq_id] = res
            return res

        if tenant_id is None:
            raise ValidationError("Tenant ID is required to create an RFQ")

        cust_uuid = _parse_uuid(data.get("customer_id"))
        if not cust_uuid:
            raise ValidationError("Valid customer_id UUID is required to create an RFQ")

        rfq = DBRFQ(
            tenant_id=tenant_id,
            rfq_number=rfq_number,
            customer_id=cust_uuid,
            origin_location_id=_parse_uuid(data.get("origin_location_id")),
            destination_location_id=_parse_uuid(data.get("destination_location_id")),
            mode=data.get("mode", "AIR"),
            service_type=data.get("service_type"),
            status="SUBMITTED",
        )
        self.session.add(rfq)
        await self.session.flush()
        return {
            "id": str(rfq.id),
            "rfq_number": rfq.rfq_number,
            "customer_id": str(rfq.customer_id),
            "mode": rfq.mode,
            "status": rfq.status,
        }

    async def get_rfq(self, rfq_id: str) -> dict[str, Any] | None:
        if self.session is None:
            return _IN_MEMORY_RFQS.get(rfq_id)

        u_id = _parse_uuid(rfq_id)
        if not u_id:
            return None
        stmt = select(DBRFQ).where(DBRFQ.id == u_id)
        result = await self.session.execute(stmt)
        rfq = result.scalar_one_or_none()
        if not rfq:
            return None
        return {
            "id": str(rfq.id),
            "rfq_number": rfq.rfq_number,
            "customer_id": str(rfq.customer_id),
            "mode": rfq.mode,
            "status": rfq.status,
            "assigned_to": str(rfq.assigned_to) if rfq.assigned_to else None,
        }

    async def assign_rfq(self, rfq_id: str, user_id: str) -> dict[str, Any] | None:
        if self.session is None:
            rfq = _IN_MEMORY_RFQS.get(rfq_id)
            if not rfq:
                return None
            rfq["assigned_to"] = user_id
            rfq["status"] = "PRICING_IN_PROGRESS"
            return rfq

        u_id = _parse_uuid(rfq_id)
        if not u_id:
            return None

        stmt = select(DBRFQ).where(DBRFQ.id == u_id)
        result = await self.session.execute(stmt)
        rfq = result.scalar_one_or_none()
        if not rfq:
            return None

        rfq.assigned_to = _parse_uuid(user_id)
        rfq.status = "PRICING_IN_PROGRESS"
        await self.session.flush()

        return {
            "id": str(rfq.id),
            "rfq_number": rfq.rfq_number,
            "customer_id": str(rfq.customer_id),
            "mode": rfq.mode,
            "status": rfq.status,
            "assigned_to": str(rfq.assigned_to) if rfq.assigned_to else None,
        }

    # =========================================================================
    # Quotations & Jobs (Phase 3)
    # =========================================================================
    async def create_quotation(
        self, data: dict[str, Any], tenant_id: uuid.UUID | None = None
    ) -> dict[str, Any]:
        q_num = data.get("quotation_number") or f"QT-{uuid.uuid4().hex[:8].upper()}"
        if self.session is None:
            q_id = str(uuid.uuid4())
            res = {
                "id": q_id,
                "quotation_number": q_num,
                "rfq_id": str(data["rfq_id"]),
                "status": "DRAFT",
                "total_amount": float(data.get("total_amount", 0.0)),
            }
            _IN_MEMORY_QUOTATIONS[q_id] = res
            return res

        rfq_uuid = _parse_uuid(data.get("rfq_id"))
        if not rfq_uuid:
            raise ValidationError("Valid rfq_id UUID is required to create a quotation")

        # Resolve tenant_id from parent RFQ if not passed
        if tenant_id is None:
            rfq_stmt = select(DBRFQ.tenant_id).where(DBRFQ.id == rfq_uuid)
            rfq_res = await self.session.execute(rfq_stmt)
            tenant_id = rfq_res.scalar_one_or_none()

        if tenant_id is None:
            raise ValidationError("Tenant ID is required to create a quotation")

        quote = DBQuotation(
            tenant_id=tenant_id,
            quotation_number=q_num,
            rfq_id=rfq_uuid,
            status="DRAFT",
            total_amount=data.get("total_amount", 0.0),
        )
        self.session.add(quote)
        await self.session.flush()
        return {
            "id": str(quote.id),
            "quotation_number": quote.quotation_number,
            "rfq_id": str(quote.rfq_id),
            "status": quote.status,
            "total_amount": float(quote.total_amount or 0.0),
        }

    async def get_quotation(self, quotation_id: str) -> dict[str, Any] | None:
        if self.session is None:
            return _IN_MEMORY_QUOTATIONS.get(quotation_id)

        u_id = _parse_uuid(quotation_id)
        if not u_id:
            return None
        stmt = select(DBQuotation).where(DBQuotation.id == u_id)
        result = await self.session.execute(stmt)
        db_quote = result.scalar_one_or_none()
        if not db_quote:
            return None
        return {
            "id": str(db_quote.id),
            "quotation_number": db_quote.quotation_number,
            "rfq_id": str(db_quote.rfq_id),
            "status": db_quote.status,
            "total_amount": float(db_quote.total_amount or 0.0),
        }

    async def accept_quotation(
        self, quotation_id: str, customer_id: str | None = None
    ) -> dict[str, Any] | None:
        if self.session is None:
            quote = _IN_MEMORY_QUOTATIONS.get(quotation_id)
            if not quote:
                return None
            quote["status"] = "ACCEPTED"
            job_number = f"JOB-{datetime.now(UTC).strftime('%y%m')}-{uuid.uuid4().hex[:5].upper()}"
            job_id = str(uuid.uuid4())
            res = {
                "job_id": job_id,
                "job_number": job_number,
                "quotation_id": quotation_id,
                "status": "CONFIRMED",
            }
            _IN_MEMORY_JOBS[job_id] = res
            return res

        u_id = _parse_uuid(quotation_id)
        if not u_id:
            return None

        stmt = select(DBQuotation).where(DBQuotation.id == u_id)
        result = await self.session.execute(stmt)
        db_quote = result.scalar_one_or_none()
        if not db_quote:
            return None

        # Update quotation state to ACCEPTED in PostgreSQL
        db_quote.status = "ACCEPTED"

        # Resolve customer_id from argument or parent RFQ
        cust_uuid = _parse_uuid(customer_id)
        if not cust_uuid and db_quote.rfq_id:
            rfq_stmt = select(DBRFQ.customer_id).where(DBRFQ.id == db_quote.rfq_id)
            rfq_res = await self.session.execute(rfq_stmt)
            cust_uuid = rfq_res.scalar_one_or_none()

        if not cust_uuid:
            raise ValidationError("Cannot accept quotation: customer_id is required")

        job_number = f"JOB-{datetime.now(UTC).strftime('%y%m')}-{uuid.uuid4().hex[:5].upper()}"
        db_job = DBJob(
            tenant_id=db_quote.tenant_id,
            job_number=job_number,
            quotation_id=db_quote.id,
            customer_id=cust_uuid,
            status="CONFIRMED",
        )
        self.session.add(db_job)
        await self.session.flush()

        return {
            "job_id": str(db_job.id),
            "job_number": db_job.job_number,
            "quotation_id": str(db_quote.id),
            "status": db_job.status,
        }
