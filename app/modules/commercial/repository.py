"""Commercial repository layer integrating with Team 1 SQLAlchemy ORM models."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
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
    RFQParty as DBRFQParty,
    RFQSpecialRequirement as DBRFQSpecialRequirement,
    JobTask as DBJobTask,
)
from app.db.models.domain import Booking, CostLine, Invoice, RevenueLine, Shipment
from app.db.models.events import OutboxEvent
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

    async def list_countries(self) -> list[dict[str, Any]]:
        if self.session is None:
            rows = {row["id"]: row for row in _IN_MEMORY_COUNTRIES.values()}.values()
            return sorted(rows, key=lambda row: row["iso_code"])
        rows = (await self.session.execute(select(DBCountry).order_by(DBCountry.iso_code))).scalars().all()
        return [
            {"id": str(row.id), "iso_code": row.iso_code, "name": row.name,
             "region": row.region or "", "trade_zone": row.trade_zone or "",
             "is_sanctioned": row.is_sanctioned, "requires_permit": row.requires_permit}
            for row in rows
        ]

    async def credit_position(self, customer_id: str, tenant_id: uuid.UUID) -> dict[str, Any] | None:
        from app.db.models.commercial import Customer as DBCustomer
        from app.db.models.domain import Invoice
        customer = (await self.session.execute(select(DBCustomer).where(
            DBCustomer.id == _parse_uuid(customer_id), DBCustomer.tenant_id == tenant_id
        ))).scalar_one_or_none()
        if not customer:
            return None
        try:
            limit = Decimal(customer.credit_limit_amount_encrypted or "0")
        except (InvalidOperation, ValueError):
            raise ValidationError("Customer credit limit is invalid")
        invoices = (await self.session.execute(select(Invoice).where(
            Invoice.customer_id == customer.id, Invoice.status.notin_(["PAID", "VOID", "CANCELLED"])
        ))).scalars().all()
        exposure = sum((Decimal(str(item.amount)) for item in invoices), Decimal("0"))
        overdue = [item for item in invoices if item.status == "OVERDUE"]
        overdue_amount = sum((Decimal(str(item.amount)) for item in overdue), Decimal("0"))
        oldest = min((item.created_at.date() for item in overdue), default=None)
        return {"customer_id": str(customer.id), "credit_limit": str(limit), "currency_code": customer.credit_limit_currency,
                "total_exposure": str(exposure), "available_credit": str(limit - exposure),
                "overdue_amount": str(overdue_amount), "oldest_invoice_date": str(oldest) if oldest else None,
                "is_blocked": exposure >= limit or bool(overdue)}

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

        provider_id = _parse_uuid(data.get("carrier_vendor_id"))
        provider_type = str(data.get("provider_type", "CARRIER")).upper()
        if provider_type not in {"CARRIER", "VENDOR"}:
            raise ValidationError("provider_type must be CARRIER or VENDOR")
        rate = DBRate(
            tenant_id=tenant_id,
            rate_number=data["rate_number"],
            rate_type=data["rate_type"],
            rate_category=data["rate_category"],
            carrier_id=provider_id if provider_type == "CARRIER" else None,
            vendor_id=provider_id if provider_type == "VENDOR" else None,
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

    async def transition_rate(self, rate_id: str, to_status: str) -> dict[str, Any] | None:
        allowed = {
            "DRAFT": {"PENDING_APPROVAL", "CANCELLED"},
            "PENDING_APPROVAL": {"APPROVED", "DRAFT", "CANCELLED"},
            "APPROVED": {"ACTIVE", "CANCELLED"},
            "ACTIVE": {"EXPIRED", "SUPERSEDED", "CANCELLED"},
            "EXPIRED": {"SUPERSEDED", "CANCELLED"},
        }
        to_status = to_status.upper()
        if self.session is None:
            rate = await self.get_rate(rate_id)
            if not rate:
                return None
            if to_status not in allowed.get(rate["status"], set()):
                raise ValidationError(f"Invalid rate transition {rate['status']} -> {to_status}")
            rate["status"] = to_status
            return rate
        uid = _parse_uuid(rate_id)
        if not uid:
            return None
        rate = (await self.session.execute(select(DBRate).where(DBRate.id == uid).with_for_update())).scalar_one_or_none()
        if not rate:
            return None
        if to_status not in allowed.get(rate.status, set()):
            raise ValidationError(f"Invalid rate transition {rate.status} -> {to_status}")
        rate.status = to_status
        await self.session.flush()
        return await self.get_rate(rate_id)

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

        mode = data.get("mode", "AIR").upper()
        service_type = data.get("service_type")
        cargo_lines = data.get("cargo_lines", [])
        containers = data.get("container_requirements", [])
        special = data.get("special_requirement") or {}
        if mode not in {"SEA", "AIR"}:
            raise ValidationError("RFQ mode must be SEA or AIR")
        if service_type == "FCL" and not containers:
            raise ValidationError("Container requirement is required for FCL shipments")
        if (mode == "AIR" or service_type in {"LCL", "DIRECT", "CONSOL"}) and not any(
            line.get("length_cm") is not None and line.get("width_cm") is not None and line.get("height_cm") is not None
            for line in cargo_lines
        ):
            raise ValidationError("Package dimensions (L/W/H) are required for LCL or Air shipments")
        if special.get("dgr_flag") and not (special.get("dgr_un_number") and special.get("dgr_class")):
            raise ValidationError("DGR UN number and class are required when DGR flag is set")
        if special.get("lc_flag") and not special.get("lc_number"):
            raise ValidationError("LC number is required when LC flag is set")
        preferred = data.get("preferred_departure")
        required = data.get("required_delivery")
        preferred_date = preferred.date() if isinstance(preferred, datetime) else preferred
        required_date = required.date() if isinstance(required, datetime) else required
        if preferred_date and preferred_date < date.today():
            raise ValidationError("Preferred departure date cannot be in the past")
        if required_date and preferred_date and required_date < preferred_date:
            raise ValidationError("Required delivery must be on or after preferred departure")

        rfq = DBRFQ(
            tenant_id=tenant_id,
            rfq_number=rfq_number,
            customer_id=cust_uuid,
            origin_location_id=_parse_uuid(data.get("origin_location_id")),
            destination_location_id=_parse_uuid(data.get("destination_location_id")),
            mode=mode,
            service_type=service_type,
            incoterm_code=data.get("incoterm_code"),
            movement_type=data.get("movement_type"),
            cargo_ready_date=data.get("cargo_ready_date"),
            preferred_departure=preferred,
            required_delivery=required,
            preferred_carrier_id=_parse_uuid(data.get("preferred_carrier_id")),
            priority=data.get("priority"),
            status="SUBMITTED",
        )
        self.session.add(rfq)
        await self.session.flush()
        for party in data.get("parties", []):
            self.session.add(DBRFQParty(
                rfq_id=rfq.id, party_role=party["party_role"], name=party["name"],
                address_encrypted=party.get("address"), contact_encrypted=party.get("contact"),
            ))
        for line in cargo_lines:
            self.session.add(DBRFQCargoLine(
                rfq_id=rfq.id, commodity_id=_parse_uuid(line.get("commodity_id")),
                package_type_code=line.get("package_type_code"), packages=line.get("packages"),
                gross_weight_kg=line.get("gross_weight_kg"), net_weight_kg=line.get("net_weight_kg"),
                volume_cbm=line.get("volume_cbm"), length_cm=line.get("length_cm"),
                width_cm=line.get("width_cm"), height_cm=line.get("height_cm"),
                cargo_value=line.get("cargo_value"), currency_code=line.get("currency_code"),
                is_stackable=line.get("is_stackable", True), is_tiltable=line.get("is_tiltable", False),
            ))
        for requirement in containers:
            self.session.add(DBRFQContainerRequirement(
                rfq_id=rfq.id, container_type_code=requirement["container_type_code"],
                quantity=requirement["quantity"], weight_per_container_kg=requirement.get("weight_per_container_kg"),
                temperature=requirement.get("temperature"), temperature_unit=requirement.get("temperature_unit"),
                genset_required=requirement.get("genset_required", False), soc_coc=requirement.get("soc_coc"),
                oog_dimensions=requirement.get("oog_dimensions"),
            ))
        if special:
            self.session.add(DBRFQSpecialRequirement(
                rfq_id=rfq.id, dgr_flag=special.get("dgr_flag", False),
                temperature_controlled=special.get("temperature_controlled", False),
                temperature_details={"un_number": special.get("dgr_un_number"), "class": special.get("dgr_class")},
                insurance_required=special.get("insurance_required", False), fumigation_required=special.get("fumigation_required", False),
                inspection_required=special.get("inspection_required", False),
                special_handling_codes=special.get("special_handling_codes"), customs_docs_required=special.get("customs_docs_required"),
                lc_flag=special.get("lc_flag", False), lc_number=special.get("lc_number"),
            ))
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
                "parent_quotation_id": data.get("parent_quotation_id"),
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

        rfq = (await self.session.execute(
            select(DBRFQ).where(DBRFQ.id == rfq_uuid, DBRFQ.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not rfq:
            raise ValidationError("RFQ not found for tenant")
        if rfq.status in {"CANCELLED", "EXPIRED", "REJECTED"}:
            raise ValidationError(f"Cannot quote RFQ in {rfq.status} status")

        pricing_date = date.today()
        rate_stmt = select(DBRate).where(
            DBRate.tenant_id == tenant_id,
            DBRate.status == "ACTIVE",
            DBRate.effective_date <= pricing_date,
            DBRate.expiry_date >= pricing_date,
            DBRate.origin_location_id == rfq.origin_location_id,
            DBRate.destination_location_id == rfq.destination_location_id,
        )
        requested_rate = _parse_uuid(data.get("rate_id"))
        if requested_rate:
            rate_stmt = rate_stmt.where(DBRate.id == requested_rate)
        applicable = (await self.session.execute(rate_stmt)).scalars().all()
        categories = ["CONTRACT_NAC", "SPOT", "LANE_NAC", "PROMOTIONAL", "FAK", "AGENT"]
        applicable.sort(key=lambda value: categories.index(value.rate_category) if value.rate_category in categories else len(categories))
        selected_rate = next((rate for rate in applicable if rate.rate_category not in {"CONTRACT_NAC", "SPOT"} or rate.customer_id == rfq.customer_id), None)
        if not selected_rate:
            raise ValidationError("NO_RATE_AVAILABLE")
        version = (await self.session.execute(
            select(DBRateVersion).where(
                DBRateVersion.rate_id == selected_rate.id,
                DBRateVersion.approval_status.in_(["APPROVED", "ACTIVE"]),
            ).order_by(DBRateVersion.version_number.desc()).limit(1)
        )).scalar_one_or_none()
        if not version:
            raise ValidationError("Selected rate has no approved version")
        rate_lines = (await self.session.execute(
            select(DBRateLine).where(DBRateLine.rate_version_id == version.id)
        )).scalars().all()
        if not rate_lines:
            raise ValidationError("Selected rate version has no charge lines")
        surcharge_lines = (await self.session.execute(
            select(DBRateSurcharge).where(
                DBRateSurcharge.rate_version_id == version.id,
                (DBRateSurcharge.applicable_from.is_(None) | (DBRateSurcharge.applicable_from <= pricing_date)),
                (DBRateSurcharge.applicable_to.is_(None) | (DBRateSurcharge.applicable_to >= pricing_date)),
            )
        )).scalars().all()
        markup = Decimal(str(data.get("markup_pct", 10))) / Decimal("100")
        expiry = data.get("expiry_date") or min(selected_rate.expiry_date, date.fromordinal(pricing_date.toordinal() + 14))
        quote = DBQuotation(
            tenant_id=tenant_id,
            quotation_number=q_num,
            rfq_id=rfq_uuid,
            status="DRAFT",
            expiry_date=expiry,
            total_amount=0,
        )
        self.session.add(quote)
        await self.session.flush()
        option = DBQuotationOption(
            quotation_id=quote.id, label="BEST_AVAILABLE", primary_rate_version_id=version.id,
            total_cost=0, total_sell=0, gross_margin=0, margin_pct=0,
            currency_code=data.get("currency_code") or selected_rate.currency_code,
        )
        self.session.add(option)
        await self.session.flush()
        total_cost = Decimal("0")
        for line in [*rate_lines, *surcharge_lines]:
            amount = Decimal(str(line.amount))
            total_cost += amount
            self.session.add(DBQuotationLine(
                quotation_option_id=option.id, charge_code=line.charge_code,
                category="SURCHARGE" if isinstance(line, DBRateSurcharge) else "FREIGHT",
                rate_version_id=version.id, cost_amount=amount,
                sell_amount=(amount * (Decimal("1") + markup)),
            ))
        total_sell = total_cost * (Decimal("1") + markup)
        option.total_cost = total_cost
        option.total_sell = total_sell
        option.gross_margin = total_sell - total_cost
        option.margin_pct = (option.gross_margin / total_sell * Decimal("100")) if total_sell else Decimal("0")
        option.is_below_margin = option.margin_pct < Decimal("5")
        quote.total_amount = total_sell
        if option.is_below_margin:
            quote.status = "BELOW_MARGIN"
        rfq.status = "QUOTED"
        await self.session.flush()
        return {
            "id": str(quote.id),
            "quotation_number": quote.quotation_number,
            "rfq_id": str(quote.rfq_id),
            "status": quote.status,
            "total_amount": float(quote.total_amount or 0.0),
            "rate_version_id": str(version.id),
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

    async def send_quotation(
        self, quotation_id: str, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ) -> dict[str, Any] | None:
        uid = _parse_uuid(quotation_id)
        if not uid:
            return None
        quote = (await self.session.execute(select(DBQuotation).where(
            DBQuotation.id == uid, DBQuotation.tenant_id == tenant_id
        ).with_for_update())).scalar_one_or_none()
        if not quote:
            return None
        if quote.status in {"CANCELLED", "EXPIRED", "ACCEPTED"} or (quote.expiry_date and quote.expiry_date < date.today()):
            raise ValidationError("Quotation cannot be sent in its current state")
        quote.status = "SENT_TO_CUSTOMER"
        quote.sent_at = datetime.now(UTC)
        self.session.add(OutboxEvent(
            event_type="quotation.sent", tenant_id=tenant_id, aggregate_type="quotation", aggregate_id=quote.id,
            payload={"quotation_id": str(quote.id), "sent_at": quote.sent_at.isoformat()},
            occurred_at=quote.sent_at, publication_status="PENDING",
        ))
        await self.session.flush()
        return await self.get_quotation(quotation_id)

    async def accept_quotation(
        self,
        quotation_id: str,
        customer_id: str | None = None,
        *,
        tenant_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
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

        if tenant_id is None or actor_id is None:
            raise ValidationError("Authenticated tenant and actor are required to accept a quotation")
        u_id = _parse_uuid(quotation_id)
        if not u_id:
            return None
        db_quote = (await self.session.execute(
            select(DBQuotation).where(
                DBQuotation.id == u_id, DBQuotation.tenant_id == tenant_id
            ).with_for_update()
        )).scalar_one_or_none()
        if not db_quote:
            return None
        if db_quote.status in {"ACCEPTED", "CANCELLED", "EXPIRED", "REJECTED"}:
            raise ValidationError(f"Quotation cannot be accepted from {db_quote.status}")
        if db_quote.expiry_date and db_quote.expiry_date < date.today():
            raise ValidationError("Quotation has expired and must be revalidated")

        rfq = (await self.session.execute(select(DBRFQ).where(DBRFQ.id == db_quote.rfq_id))).scalar_one()
        cust_uuid = _parse_uuid(customer_id) or rfq.customer_id
        from app.db.models.commercial import Customer as DBCustomer
        customer = (await self.session.execute(
            select(DBCustomer).where(DBCustomer.id == cust_uuid, DBCustomer.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not customer:
            raise ValidationError("Customer does not belong to this tenant")
        try:
            credit_limit = Decimal(customer.credit_limit_amount_encrypted or "0")
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Customer credit limit is not configured") from exc
        invoices = (await self.session.execute(
            select(Invoice).where(
                Invoice.customer_id == cust_uuid,
                Invoice.status.notin_(["PAID", "VOID", "CANCELLED"]),
            )
        )).scalars().all()
        exposure = sum((Decimal(str(invoice.amount)) for invoice in invoices), Decimal("0"))
        new_exposure = exposure + Decimal(str(db_quote.total_amount or 0))
        if new_exposure > credit_limit:
            raise ValidationError("CREDIT_LIMIT_EXCEEDED", errors=[{
                "code": "CREDIT_LIMIT_EXCEEDED", "current_exposure": str(exposure),
                "new_exposure": str(new_exposure),
            }])

        rate_rows = (await self.session.execute(
            select(DBRateVersion, DBRate)
            .join(DBQuotationOption, DBQuotationOption.primary_rate_version_id == DBRateVersion.id)
            .join(DBRate, DBRate.id == DBRateVersion.rate_id)
            .where(DBQuotationOption.quotation_id == db_quote.id)
        )).all()
        if not rate_rows:
            raise ValidationError("Quotation has no rate-version-backed option")
        for version, rate in rate_rows:
            if version.approval_status not in {"APPROVED", "ACTIVE"} or rate.status != "ACTIVE" or not (rate.effective_date <= date.today() <= rate.expiry_date):
                raise ValidationError("A quotation rate is no longer valid")

        # Country sanctions are the configured local embargo source.  Party
        # name screening is not pretended when no sanctions-list integration exists.
        country_ids = (await self.session.execute(
            select(DBCountry.id).join(DBLocation, DBLocation.country_id == DBCountry.id).where(
                DBLocation.id.in_([rfq.origin_location_id, rfq.destination_location_id]),
                DBCountry.is_sanctioned.is_(True),
            )
        )).all()
        if country_ids:
            raise ValidationError("EMBARGO_RESTRICTION")

        prefix = f"HQ-{rfq.mode}-EXP-{datetime.now(UTC).strftime('%y%m')}-"
        count = (await self.session.execute(
            select(func.count()).select_from(DBJob).where(
                DBJob.tenant_id == tenant_id, DBJob.job_number.like(f"{prefix}%")
            )
        )).scalar_one()
        db_quote.status = "ACCEPTED"
        db_job = DBJob(
            tenant_id=tenant_id, job_number=f"{prefix}{count + 1:05d}",
            quotation_id=db_quote.id, customer_id=cust_uuid, status="CONFIRMED", created_by=actor_id,
        )
        self.session.add(db_job)
        await self.session.flush()
        booking = Booking(tenant_id=tenant_id, quotation_id=db_quote.id, status="BOOKED", booked_at=datetime.now(UTC))
        self.session.add(booking)
        await self.session.flush()
        shipment = Shipment(
            tenant_id=tenant_id, booking_id=booking.id, job_id=db_job.id,
            customer_id=cust_uuid, mode=rfq.mode, status="BOOKED", created_by=actor_id,
        )
        self.session.add(shipment)
        options = (await self.session.execute(select(DBQuotationOption).where(DBQuotationOption.quotation_id == db_quote.id))).scalars().all()
        option_ids = [option.id for option in options]
        lines = (await self.session.execute(
            select(DBQuotationLine).where(DBQuotationLine.quotation_option_id.in_(option_ids))
        )).scalars().all() if option_ids else []
        for line in lines:
            self.session.add(RevenueLine(shipment_id=shipment.id, charge_code=line.charge_code, amount=line.sell_amount, status="ESTIMATED"))
            self.session.add(CostLine(shipment_id=shipment.id, charge_code=line.charge_code, amount=line.cost_amount, status="ESTIMATED"))
        for department, task_type in (("DOCUMENTATION", "DOCUMENT_CHECKLIST"), ("OPERATIONS", "BOOKING_HANDOFF")):
            self.session.add(DBJobTask(tenant_id=tenant_id, job_id=db_job.id, department=department, task_type=task_type, created_by=actor_id))
        self.session.add(OutboxEvent(
            event_type="booking.confirmed", tenant_id=tenant_id, aggregate_type="job", aggregate_id=db_job.id,
            payload={"job_id": str(db_job.id), "shipment_id": str(shipment.id), "quotation_id": str(db_quote.id)},
            occurred_at=datetime.now(UTC), publication_status="PENDING",
        ))
        await self.session.flush()
        return {"job_id": str(db_job.id), "job_number": db_job.job_number, "quotation_id": str(db_quote.id), "shipment_id": str(shipment.id), "status": db_job.status}
