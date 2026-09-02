"""Async SQLAlchemy engine, session factory, and tenant context management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url_async,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def set_tenant_context(
    session: AsyncSession, tenant_id: UUID, customer_id: UUID | None = None
) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    if customer_id:
        await session.execute(
            text("SELECT set_config('app.customer_id', :customer_id, true)"),
            {"customer_id": str(customer_id)},
        )


async def reset_tenant_context(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    await session.execute(text("SELECT set_config('app.customer_id', '', true)"))


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await reset_tenant_context(session)
            await session.close()
