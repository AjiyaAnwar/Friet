"""Identity and RBAC service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_PERMISSION_MAP, SYSTEM_PERMISSIONS, SystemRole
from app.db.models.identity import (
    Permission,
    Role,
    RolePermission,
    Tenant,
    UserBranchRole,
)


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tenant_by_code(self, code: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.code == code))
        return result.scalar_one_or_none()

    async def get_user_permissions_and_roles(
        self, user_id: uuid.UUID
    ) -> tuple[set[str], set[str]]:
        result = await self.session.execute(
            select(UserBranchRole, Role)
            .join(Role, Role.id == UserBranchRole.role_id)
            .where(UserBranchRole.user_id == user_id)
        )
        permissions: set[str] = set()
        roles: set[str] = set()
        for _ubr, role in result.all():
            roles.add(role.code)
            perms = await self._role_permissions(role.id)
            permissions.update(p.code for p in perms)
            if role.code in SystemRole.__members__:
                permissions.update(ROLE_PERMISSION_MAP.get(SystemRole(role.code), set()))
        return permissions, roles

    async def _role_permissions(self, role_id: uuid.UUID) -> list[Permission]:
        result = await self.session.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return list(result.scalars())

    async def seed_system_permissions(self) -> None:
        for code, resource, action in SYSTEM_PERMISSIONS:
            existing = await self.session.execute(
                select(Permission).where(Permission.code == code)
            )
            if existing.scalar_one_or_none():
                continue
            self.session.add(
                Permission(code=code, resource=resource, action=action, description=code)
            )

    async def seed_system_roles_for_tenant(self, tenant_id: uuid.UUID) -> None:
        for role_enum in SystemRole:
            existing = await self.session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.code == role_enum.value)
            )
            if existing.scalar_one_or_none():
                continue
            role = Role(
                tenant_id=tenant_id,
                name=role_enum.value.replace("_", " ").title(),
                code=role_enum.value,
                is_system_role=True,
            )
            self.session.add(role)
            await self.session.flush()
            perm_codes = ROLE_PERMISSION_MAP.get(role_enum, set())
            if role_enum == SystemRole.SUPER_ADMIN:
                perm_codes = {p[0] for p in SYSTEM_PERMISSIONS}
            for code in perm_codes:
                perm_result = await self.session.execute(
                    select(Permission).where(Permission.code == code)
                )
                perm = perm_result.scalar_one_or_none()
                if perm:
                    self.session.add(RolePermission(role_id=role.id, permission_id=perm.id))
