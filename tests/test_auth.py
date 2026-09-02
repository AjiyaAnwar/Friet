"""Authentication integration tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_refresh_logout(client: AsyncClient):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@freightcore.local", "password": "ChangeMe123!"},
        headers={"X-Tenant-Code": "default"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert "access_token" in tokens

    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "admin@freightcore.local"

    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    new_tokens = refresh.json()

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout.status_code == 204

    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert reuse.status_code == 401
