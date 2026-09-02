"""HTTP middleware: correlation IDs, rate limits, idempotency."""

import json
import uuid
from collections.abc import Callable

from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.exceptions import problem_detail
from app.modules.redis.service import redis_service, request_fingerprint


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        maximum = get_settings().max_request_bytes
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > maximum
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content=problem_detail(
                        type_slug="request-too-large",
                        title="Request too large",
                        status=413,
                        detail=f"Request body exceeds the {maximum}-byte limit.",
                        instance=request.url.path,
                        correlation_id=getattr(request.state, "correlation_id", None),
                    ),
                )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        if request.url.path.startswith("/health"):
            return await call_next(request)

        if request.url.path.endswith("/auth/login"):
            limit = settings.rate_limit_unauth
            key = f"ip:{request.client.host if request.client else 'unknown'}"
        else:
            limit = settings.rate_limit_internal
            key = f"user:{request.headers.get('Authorization', 'anon')[:32]}"

        try:
            max_limit, remaining, reset = await redis_service.check_rate_limit(key, limit)
        except RedisError:
            return await call_next(request)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method != "POST":
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key or request.url.path.startswith("/health"):
            return await call_next(request)

        body = await request.body()

        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # type: ignore[attr-defined]

        tenant = request.headers.get("X-Tenant-Code", "default")
        scope = f"{tenant}:{request.url.path}:{idempotency_key}"
        fingerprint = request_fingerprint(request.method, request.url.path, body)

        try:
            cached = await redis_service.store_idempotency(
                scope_key=scope,
                request_fingerprint=fingerprint,
                response_body={},
                status_code=200,
            )
            if cached:
                return Response(
                    content=json.dumps(cached["body"]),
                    status_code=cached["status_code"],
                    media_type="application/json",
                )
        except RedisError:
            # Redis outages fail open; semantic idempotency conflicts still propagate.
            cached = None

        response = await call_next(request)
        if response.status_code < 500:
            content = b""
            async for chunk in response.body_iterator:
                content += chunk
            try:
                body_json = json.loads(content.decode()) if content else {}
            except json.JSONDecodeError:
                body_json = {"raw": content.decode()}
            await redis_service.store_idempotency(
                scope_key=scope,
                request_fingerprint=fingerprint,
                response_body=body_json,
                status_code=response.status_code,
            )
            return Response(
                content=content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        return response
