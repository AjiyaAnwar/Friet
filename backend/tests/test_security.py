"""Security unit tests."""

from app.core.security import (
    create_access_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    hash_token,
    verify_password,
    verify_totp,
)


def test_password_hashing():
    hashed = hash_password("SecurePass123!")
    assert verify_password("SecurePass123!", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    import uuid

    token = create_access_token(
        subject=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )
    payload = decode_token(token)
    assert payload["type"] == "access"


def test_token_hash_deterministic():
    assert hash_token("abc") == hash_token("abc")


def test_totp():
    secret = generate_totp_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)
