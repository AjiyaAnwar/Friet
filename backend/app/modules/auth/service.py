"""Authentication business logic."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decrypt_value,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_recovery_code,
    hash_token,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.db.models.identity import RefreshToken, User
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    LoginRequest,
    MfaEnrollResponse,
    TokenResponse,
    UserMeResponse,
)
from app.modules.identity.service import IdentityService


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = AuthRepository(session)
        self.identity = IdentityService(session)

    async def login(
        self,
        tenant_code: str,
        payload: LoginRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        tenant = await self.identity.get_tenant_by_code(tenant_code)
        if not tenant:
            raise UnauthorizedError("Invalid credentials")

        user = await self.repo.get_user_by_email(tenant.id, payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            if user:
                await self._record_failed_login(user)
            raise UnauthorizedError("Invalid credentials")

        if user.status != "ACTIVE":
            raise ForbiddenError("Account is not active")

        if user.locked_until and user.locked_until > datetime.now(UTC):
            raise ForbiddenError("Account is locked")

        if user.mfa_enabled:
            if not payload.totp_code:
                raise ValidationError("MFA code required", errors=[{"field": "totp_code"}])
            secret = decrypt_value(user.mfa_secret_encrypted or "", self.settings)
            if not verify_totp(secret, payload.totp_code):
                raise UnauthorizedError("Invalid MFA code")

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(UTC)

        response, _ = await self._issue_tokens(
            user, ip_address=ip_address, user_agent=user_agent
        )
        return response

    async def refresh(self, refresh_token: str) -> TokenResponse:
        claims = decode_token(refresh_token, self.settings)
        if claims.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token")
        token_hash = hash_token(refresh_token)
        stored = await self.repo.get_refresh_token_by_hash(token_hash)
        if not stored or stored.revoked_at or stored.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Invalid refresh token")

        try:
            token_tenant_id = uuid.UUID(str(claims["tenant_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        user = await self.repo.get_user_by_id(stored.user_id, token_tenant_id)
        if not user:
            raise UnauthorizedError("Invalid refresh token")
        if user.status != "ACTIVE":
            raise ForbiddenError("Account is not active")

        stored.revoked_at = datetime.now(UTC)
        response, replacement_id = await self._issue_tokens(user)
        stored.replaced_by_id = replacement_id
        return response

    async def logout(self, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        stored = await self.repo.get_refresh_token_by_hash(token_hash)
        if stored and not stored.revoked_at:
            stored.revoked_at = datetime.now(UTC)

    async def get_me(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> UserMeResponse:
        user = await self.repo.get_user_by_id(user_id, tenant_id)
        if not user:
            raise UnauthorizedError("User not found")
        permissions, roles = await self.identity.get_user_permissions_and_roles(user.id)
        return UserMeResponse(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            mfa_enabled=user.mfa_enabled,
            permissions=sorted(permissions),
            roles=sorted(roles),
            last_login_at=user.last_login_at,
        )

    async def enroll_mfa(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> MfaEnrollResponse:
        user = await self.repo.get_user_by_id(user_id, tenant_id)
        if not user:
            raise UnauthorizedError("User not found")
        secret = generate_totp_secret()
        recovery = generate_recovery_codes()
        user.mfa_secret_encrypted = self._encrypt(secret)
        user.mfa_recovery_hashes = [hash_recovery_code(c) for c in recovery]
        user.mfa_enabled = False
        return MfaEnrollResponse(
            secret=secret,
            provisioning_uri=totp_provisioning_uri(secret, user.email),
            recovery_codes=recovery,
        )

    async def confirm_mfa(self, user_id: uuid.UUID, tenant_id: uuid.UUID, code: str) -> None:
        user = await self.repo.get_user_by_id(user_id, tenant_id)
        if not user or not user.mfa_secret_encrypted:
            raise ValidationError("MFA enrollment not started")
        secret = decrypt_value(user.mfa_secret_encrypted, self.settings)
        if not verify_totp(secret, code):
            raise ValidationError("Invalid MFA code")
        user.mfa_enabled = True

    async def _issue_tokens(
        self,
        user: User,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[TokenResponse, uuid.UUID]:
        token_id = uuid.uuid4()
        access = create_access_token(
            subject=user.id,
            tenant_id=user.tenant_id,
            token_id=token_id,
            settings=self.settings,
        )
        refresh = create_refresh_token(
            subject=user.id,
            tenant_id=user.tenant_id,
            token_id=token_id,
            settings=self.settings,
        )
        refresh_row = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC)
            + timedelta(days=self.settings.refresh_token_expire_days),
            ip_address=ip_address,
            device_info=user_agent,
        )
        await self.repo.save_refresh_token(refresh_row)
        response = TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=self.settings.access_token_expire_minutes * 60,
        )
        return response, refresh_row.id

    async def _record_failed_login(self, user: User) -> None:
        user.failed_login_count += 1
        if user.failed_login_count >= self.settings.max_failed_login_attempts:
            user.locked_until = datetime.now(UTC) + timedelta(
                minutes=self.settings.account_lockout_minutes
            )

    def _encrypt(self, value: str) -> str:
        from app.core.security import encrypt_value

        return encrypt_value(value, self.settings)

    @staticmethod
    def hash_password(password: str) -> str:
        return hash_password(password)
