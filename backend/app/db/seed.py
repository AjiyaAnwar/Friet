"""Database seed utilities for development and tests."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import SystemRole
from app.db.models.identity import Branch, Company, Role, Tenant, User, UserBranchRole
from app.modules.auth.service import AuthService
from app.modules.identity.service import IdentityService
from app.db.models.reference import ContainerType, Incoterm


INCOTERMS_2020 = {
    "EXW": "Ex Works", "FCA": "Free Carrier", "CPT": "Carriage Paid To",
    "CIP": "Carriage and Insurance Paid To", "DAP": "Delivered At Place",
    "DPU": "Delivered at Place Unloaded", "DDP": "Delivered Duty Paid",
    "FAS": "Free Alongside Ship", "FOB": "Free On Board",
    "CFR": "Cost and Freight", "CIF": "Cost Insurance and Freight",
}
CONTAINER_SPECS = {
    "20GP": (33.2, 28200), "40GP": (67.7, 26700), "40HC": (76.3, 26500),
    "20RF": (28.3, 27700), "40RF": (59.3, 29500), "20OT": (32.0, 28000),
    "40OT": (65.0, 26000), "20FR": (28.0, 27000), "40FR": (55.0, 39000),
}


async def seed_commercial_reference_data(session: AsyncSession) -> None:
    """Idempotently seed standards-owned commercial reference data."""
    for code, name in INCOTERMS_2020.items():
        if not (await session.execute(select(Incoterm.code).where(Incoterm.code == code))).scalar_one_or_none():
            session.add(Incoterm(code=code, name=name))
    for code, (cbm, payload) in CONTAINER_SPECS.items():
        if not (await session.execute(select(ContainerType.code).where(ContainerType.code == code))).scalar_one_or_none():
            session.add(ContainerType(code=code, cbm_capacity=cbm, max_payload_kg=payload))
    await session.flush()


async def seed_platform(session: AsyncSession) -> dict[str, uuid.UUID | str]:
    identity = IdentityService(session)
    await seed_commercial_reference_data(session)
    await identity.seed_system_permissions()

    tenant = await identity.get_tenant_by_code("default")
    if not tenant:
        tenant = Tenant(code="default", name="Default Tenant", status="ACTIVE")
        session.add(tenant)
        await session.flush()

    company_result = await session.execute(
        select(Company).where(Company.tenant_id == tenant.id, Company.code == "HQ")
    )
    company = company_result.scalar_one_or_none()
    if not company:
        company = Company(
            tenant_id=tenant.id,
            legal_name="Inter-Fret Consolidators",
            code="HQ",
            base_currency="USD",
            country_code="PK",
        )
        session.add(company)
        await session.flush()

    branch_result = await session.execute(
        select(Branch).where(Branch.tenant_id == tenant.id, Branch.code == "KHI")
    )
    branch = branch_result.scalar_one_or_none()
    if not branch:
        branch = Branch(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Karachi HQ",
            code="KHI",
            timezone="Asia/Karachi",
        )
        session.add(branch)
        await session.flush()

    await identity.seed_system_roles_for_tenant(tenant.id)

    admin_result = await session.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == "admin@freightcore.local")
    )
    admin = admin_result.scalar_one_or_none()
    if not admin:
        admin = User(
            tenant_id=tenant.id,
            email="admin@freightcore.local",
            password_hash=AuthService.hash_password("ChangeMe123!"),
            full_name="System Administrator",
            status="ACTIVE",
        )
        session.add(admin)
        await session.flush()

        super_role = await session.execute(
            select(Role).where(Role.tenant_id == tenant.id, Role.code == SystemRole.SUPER_ADMIN)
        )
        role = super_role.scalar_one()
        session.add(UserBranchRole(user_id=admin.id, branch_id=branch.id, role_id=role.id))

    await session.commit()
    return {"tenant_id": tenant.id, "admin_email": "admin@freightcore.local"}


if __name__ == "__main__":
    from app.db.session import AsyncSessionLocal

    async def main() -> None:
        async with AsyncSessionLocal() as session:
            result = await seed_platform(session)
            print(result)

    asyncio.run(main())
