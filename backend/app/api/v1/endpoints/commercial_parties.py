"""Tenant-scoped commercial party master APIs using existing ERD entities."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.core.exceptions import NotFoundError
from app.db.models.commercial import Agent, Customer, CustomerContact, CustomerCreditOverride, Vendor
from app.db.session import get_db

router = APIRouter()


class CustomerCreate(BaseModel):
    name: str
    credit_limit_amount: Decimal = Field(ge=0)
    credit_limit_currency: str = "USD"
    payment_terms_days: int = Field(default=30, ge=0)
    credit_tier: str = "NEW"
    tax_registration: str | None = None
    registration_number: str | None = None
    iata_fiata_membership: str | None = None
    preferred_lanes: dict | None = None
    preferred_service_types: dict | None = None
    kyc_status: str = "PENDING"
    onboarding_date: date | None = None


class VendorCreate(BaseModel):
    name: str
    vendor_type: str
    tax_registration: str | None = None
    bank_details: str | None = None
    payment_terms: int | None = Field(None, ge=0)


class AgentCreate(BaseModel):
    vendor_id: uuid.UUID | None = None
    coverage_country_id: uuid.UUID | None = None
    coverage_city: str | None = None
    services_provided: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    settlement_model: str = "INVOICE"


class CreditOverrideCreate(BaseModel):
    reason: str
    valid_from: date
    valid_to: date


@router.post("/customers")
async def create_customer(
    payload: CustomerCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:approve"))],
) -> dict:
    count = (await session.execute(select(func.count()).select_from(Customer).where(Customer.tenant_id == user.tenant_id))).scalar_one()
    customer = Customer(
        tenant_id=user.tenant_id, customer_code=f"CUST-{count + 1:04d}", name=payload.name,
        credit_limit_amount_encrypted=str(payload.credit_limit_amount), credit_limit_currency=payload.credit_limit_currency,
        payment_terms_days=payload.payment_terms_days, credit_tier=payload.credit_tier,
        tax_registration_encrypted=payload.tax_registration, registration_number=payload.registration_number,
        iata_fiata_membership=payload.iata_fiata_membership, preferred_lanes=payload.preferred_lanes,
        preferred_service_types=payload.preferred_service_types, kyc_status=payload.kyc_status,
        onboarding_date=payload.onboarding_date or date.today(), created_by=user.id,
    )
    session.add(customer); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(customer.id), "customer_code": customer.customer_code, "name": customer.name}, "errors": [], "meta": {}}


@router.post("/vendors")
async def create_vendor(
    payload: VendorCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    count = (await session.execute(select(func.count()).select_from(Vendor).where(Vendor.tenant_id == user.tenant_id))).scalar_one()
    vendor = Vendor(tenant_id=user.tenant_id, vendor_code=f"VEND-{count + 1:04d}", name=payload.name,
                    vendor_type=payload.vendor_type, tax_registration_encrypted=payload.tax_registration,
                    bank_details_encrypted=payload.bank_details, payment_terms=payload.payment_terms, created_by=user.id)
    session.add(vendor); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(vendor.id), "vendor_code": vendor.vendor_code, "name": vendor.name}, "errors": [], "meta": {}}


@router.post("/agents")
async def create_agent(
    payload: AgentCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:create"))],
) -> dict:
    if payload.vendor_id and not (await session.execute(select(Vendor.id).where(Vendor.id == payload.vendor_id, Vendor.tenant_id == user.tenant_id))).scalar_one_or_none():
        raise NotFoundError("Vendor not found")
    agent = Agent(tenant_id=user.tenant_id, **payload.model_dump())
    session.add(agent); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(agent.id), "settlement_model": agent.settlement_model}, "errors": [], "meta": {}}


class CreditLimitUpdate(BaseModel):
    credit_limit_amount: Decimal = Field(ge=0)
    credit_limit_currency: str = "USD"


@router.post("/customers/{customer_id}/credit-overrides")
async def create_credit_override(
    customer_id: uuid.UUID,
    payload: CreditOverrideCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
) -> dict:
    if "FINANCE_CONTROLLER" not in user.roles:
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("Finance Controller role is required")
    if payload.valid_to < payload.valid_from:
        raise ValueError("valid_to must be on or after valid_from")
    if not (await session.execute(select(Customer.id).where(Customer.id == customer_id, Customer.tenant_id == user.tenant_id))).scalar_one_or_none():
        raise NotFoundError("Customer not found")
    override = CustomerCreditOverride(customer_id=customer_id, reason=payload.reason, approved_by=user.id,
                                      valid_from=payload.valid_from, valid_to=payload.valid_to)
    session.add(override); await session.flush(); await session.commit()
    return {"success": True, "data": {"id": str(override.id), "customer_id": str(customer_id), "valid_to": str(override.valid_to)}, "errors": [], "meta": {}}


@router.patch("/customers/{customer_id}/credit-limit")
async def update_customer_credit_limit(
    customer_id: uuid.UUID,
    payload: CreditLimitUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("finance:read"))],
) -> dict:
    if "FINANCE_CONTROLLER" not in user.roles and not user.is_superadmin:
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("Finance Controller role is required to update credit limits")
    customer = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not customer:
        raise NotFoundError("Customer not found")
    customer.credit_limit_amount_encrypted = str(payload.credit_limit_amount)
    customer.credit_limit_currency = payload.credit_limit_currency
    await session.flush()
    await session.commit()
    return {
        "success": True,
        "data": {
            "id": str(customer.id),
            "credit_limit_amount": str(payload.credit_limit_amount),
            "credit_limit_currency": payload.credit_limit_currency,
        },
        "errors": [],
        "meta": {},
    }


@router.get("/customers")
async def list_customers(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
    q: str = "",
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    stmt = select(Customer).where(Customer.tenant_id == user.tenant_id).order_by(Customer.name)
    customers = (await session.execute(stmt)).scalars().all()
    if q:
        customers = [c for c in customers if q.lower() in c.name.lower() or (c.customer_code and q.lower() in c.customer_code.lower())]
    return {
        "success": True,
        "data": [
            {
                "id": str(c.id),
                "customer_code": c.customer_code,
                "name": c.name,
                "credit_tier": c.credit_tier,
                "credit_limit_currency": c.credit_limit_currency,
                "payment_terms_days": c.payment_terms_days,
                "kyc_status": c.kyc_status,
                "is_active": c.is_active,
            }
            for c in customers
        ],
        "errors": [],
        "meta": {"total": len(customers)},
    }


@router.get("/customers/{customer_id}")
async def get_customer(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("quotation:read"))],
) -> dict:
    if session is None:
        raise NotFoundError("Customer not found")
    customer = (await session.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not customer:
        raise NotFoundError("Customer not found")
    return {
        "success": True,
        "data": {
            "id": str(customer.id),
            "customer_code": customer.customer_code,
            "name": customer.name,
            "credit_tier": customer.credit_tier,
            "credit_limit_currency": customer.credit_limit_currency,
            "payment_terms_days": customer.payment_terms_days,
            "kyc_status": customer.kyc_status,
            "is_active": customer.is_active,
            "registration_number": customer.registration_number,
            "iata_fiata_membership": customer.iata_fiata_membership,
            "onboarding_date": str(customer.onboarding_date) if customer.onboarding_date else None,
        },
        "errors": [],
        "meta": {},
    }


@router.get("/vendors")
async def list_vendors(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
    vendor_type: str | None = None,
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    stmt = select(Vendor).where(Vendor.tenant_id == user.tenant_id).order_by(Vendor.name)
    if vendor_type:
        stmt = stmt.where(Vendor.vendor_type == vendor_type.upper())
    vendors = (await session.execute(stmt)).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(v.id),
                "vendor_code": v.vendor_code,
                "name": v.name,
                "vendor_type": v.vendor_type,
                "payment_terms": v.payment_terms,
                "is_active": v.is_active,
            }
            for v in vendors
        ],
        "errors": [],
        "meta": {"total": len(vendors)},
    }


@router.get("/vendors/{vendor_id}")
async def get_vendor(
    vendor_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    if session is None:
        raise NotFoundError("Vendor not found")
    vendor = (await session.execute(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not vendor:
        raise NotFoundError("Vendor not found")
    return {
        "success": True,
        "data": {
            "id": str(vendor.id),
            "vendor_code": vendor.vendor_code,
            "name": vendor.name,
            "vendor_type": vendor.vendor_type,
            "payment_terms": vendor.payment_terms,
            "is_active": vendor.is_active,
        },
        "errors": [],
        "meta": {},
    }


@router.get("/agents")
async def list_agents(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    if session is None:
        return {"success": True, "data": [], "errors": [], "meta": {"total": 0}}
    agents = (await session.execute(
        select(Agent).where(Agent.tenant_id == user.tenant_id)
    )).scalars().all()
    return {
        "success": True,
        "data": [
            {
                "id": str(a.id),
                "vendor_id": str(a.vendor_id) if a.vendor_id else None,
                "coverage_country_id": str(a.coverage_country_id) if a.coverage_country_id else None,
                "coverage_city": a.coverage_city,
                "services_provided": a.services_provided,
                "settlement_model": a.settlement_model,
                "is_active": a.is_active,
            }
            for a in agents
        ],
        "errors": [],
        "meta": {"total": len(agents)},
    }


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("rate:read"))],
) -> dict:
    agent = (await session.execute(
        select(Agent).where(Agent.id == agent_id, Agent.tenant_id == user.tenant_id)
    )).scalar_one_or_none()
    if not agent:
        raise NotFoundError("Agent not found")
    return {
        "success": True,
        "data": {
            "id": str(agent.id),
            "vendor_id": str(agent.vendor_id) if agent.vendor_id else None,
            "coverage_country_id": str(agent.coverage_country_id) if agent.coverage_country_id else None,
            "coverage_city": agent.coverage_city,
            "services_provided": agent.services_provided,
            "certifications": agent.certifications,
            "settlement_model": agent.settlement_model,
            "is_active": agent.is_active,
        },
        "errors": [],
        "meta": {},
    }
