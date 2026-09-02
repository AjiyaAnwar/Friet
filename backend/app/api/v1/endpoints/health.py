"""Health check endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db.session import engine
from app.modules.redis.service import redis_service

router = APIRouter()


@router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:  # noqa: BLE001 - readiness must convert dependency failures to status
        checks["postgres"] = "unavailable"
        healthy = False

    try:
        await redis_service.client.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001 - readiness must convert dependency failures to status
        checks["redis"] = "unavailable"
        healthy = False

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
