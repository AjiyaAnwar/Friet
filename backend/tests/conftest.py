"""Pytest configuration and fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.seed import seed_platform
from app.main import app
from app.modules.redis.service import redis_service

# Test env overrides
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-min-32-characters-long")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-fernet-dev-only")
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "hijal"
os.environ["POSTGRES_DB"] = "freightcore_test"
os.environ.setdefault("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15"))

get_settings.cache_clear()


@pytest_asyncio.fixture
async def engine():
    settings = get_settings()
    test_engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded(session: AsyncSession):
    return await seed_platform(session)


@pytest_asyncio.fixture
async def client(engine, seeded) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    await redis_service.connect()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await redis_service.close()