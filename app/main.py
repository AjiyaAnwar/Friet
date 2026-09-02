"""FreightCore FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import FreightCoreError, problem_detail
from app.core.logging import configure_logging
from app.middleware.http import (
    CorrelationMiddleware,
    IdempotencyMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
)
from app.modules.redis.service import redis_service
from app.modules.search.service import search_service

REQUEST_COUNT = Counter("freightcore_requests_total", "Total HTTP requests", ["method", "path", "status"])

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await redis_service.connect()
    try:
        await search_service.connect()
        await search_service.ensure_indices()
    except Exception:  # noqa: BLE001 - search is optional at API startup; readiness reports it
        search_service.mark_unavailable()
    yield
    await search_service.close()
    await redis_service.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(IdempotencyMiddleware)


@app.exception_handler(FreightCoreError)
async def freightcore_error_handler(request: Request, exc: FreightCoreError) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    body = problem_detail(
        type_slug=exc.type_slug,
        title=exc.type_slug.replace("-", " ").title(),
        status=exc.status_code,
        detail=exc.message,
        instance=str(request.url.path),
        correlation_id=correlation_id,
        errors=exc.errors,
    )
    headers = {}
    if exc.type_slug == "rate-limit":
        headers["Retry-After"] = str(getattr(exc, "retry_after", 60))
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", None)
    body = problem_detail(
        type_slug="validation-error",
        title="Validation failed",
        status=422,
        detail="One or more fields are invalid.",
        instance=str(request.url.path),
        correlation_id=correlation_id,
        errors=list(exc.errors()),
    )
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a stable problem response without leaking implementation details."""
    body = problem_detail(
        type_slug="internal-error",
        title="Internal server error",
        status=500,
        detail="An unexpected error occurred.",
        instance=str(request.url.path),
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return JSONResponse(status_code=500, content=body)


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health/live", include_in_schema=False)
async def root_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
async def root_ready() -> JSONResponse:
    from app.api.v1.endpoints.health import readiness

    return await readiness()  # type: ignore[return-value]


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    response = await call_next(request)
    REQUEST_COUNT.labels(request.method, request.url.path, str(response.status_code)).inc()
    return response
