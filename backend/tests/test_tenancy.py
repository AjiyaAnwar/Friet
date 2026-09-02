"""Tenant isolation tests."""


import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import SystemRole
from app.db.models.identity import Branch, Company, Role, Tenant, User, UserBranchRole
from app.modules.auth.service import AuthService


@pytest.mark.asyncio
async def test_tenant_isolation(client: AsyncClient, session: AsyncSession, seeded):
    tenant_b = Tenant(code="tenant-b", name="Tenant B", status="ACTIVE")
    session.add(tenant_b)
    await session.flush()

    company = Company(
        tenant_id=tenant_b.id,
        legal_name="Tenant B Co",
        code="B1",
        base_currency="USD",
        country_code="PK",
    )
    session.add(company)
    await session.flush()
    branch = Branch(
        tenant_id=tenant_b.id,
        company_id=company.id,
        name="Branch B",
        code="B1",
    )
    session.add(branch)
    await session.flush()

    role = Role(
        tenant_id=tenant_b.id,
        name="Sales",
        code=SystemRole.SALES.value,
        is_system_role=True,
    )
    session.add(role)
    await session.flush()

    user_b = User(
        tenant_id=tenant_b.id,
        email="sales-b@freightcore.local",
        password_hash=AuthService.hash_password("ChangeMe123!"),
        full_name="Sales B",
    )
    session.add(user_b)
    await session.flush()
    session.add(UserBranchRole(user_id=user_b.id, branch_id=branch.id, role_id=role.id))
    await session.commit()

    login_a = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@freightcore.local", "password": "ChangeMe123!"},
        headers={"X-Tenant-Code": "default"},
    )
    assert login_a.status_code == 200, login_a.text
    token_a = login_a.json()["access_token"]

    users = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    emails = [u["email"] for u in users.json()["data"]]
    assert "sales-b@freightcore.local" not in emails
