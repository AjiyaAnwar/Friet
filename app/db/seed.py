"""Database seed utilities for development and tests."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import SystemRole
from app.db.models.identity import Branch, Company, Role, Tenant, User, UserBranchRole
from app.modules.auth.service import AuthService
from app.modules.identity.service import IdentityService


async def seed_platform(session: AsyncSession) -> dict[str, uuid.UUID | str]:
    identity = IdentityService(session)
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
