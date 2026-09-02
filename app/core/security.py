"""Security utilities: password hashing, JWT, TOTP MFA, and column encryption."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import pyotp
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.core.config import Settings, get_settings


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet(settings: Settings | None = None) -> Fernet:
    settings = settings or get_settings()
    key = settings.encryption_key.encode()
    try:
        return Fernet(key)
    except (TypeError, ValueError):
        # Dev fallback: derive a valid Fernet key from secret
        derived = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
        return Fernet(derived)


def encrypt_value(plaintext: str, settings: Settings | None = None) -> str:
    return _fernet(settings).encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, settings: Settings | None = None) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt value") from exc


def lookup_hash(value: str) -> str:
    normalized = value.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def create_access_token(
    *,
    subject: UUID,
    tenant_id: UUID,
    token_id: UUID,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = settings or get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "jti": str(token_id),
        "exp": expire,
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    *,
    subject: UUID,
    tenant_id: UUID,
    token_id: UUID,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "jti": str(token_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str, issuer: str = "FreightCore") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_hex(4) for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()
