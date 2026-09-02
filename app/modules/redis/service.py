"""Redis-backed rate limiting, idempotency, and distributed locks."""

import hashlib
import json
import time
import uuid
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.exceptions import IdempotencyConflictError, RateLimitError

settings = get_settings()


class RedisService:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._client = redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected")
        return self._client

    async def check_rate_limit(
        self, key: str, limit: int, window_seconds: int = 60
    ) -> tuple[int, int, int]:
        now = int(time.time())
        window_key = f"rl:{key}:{now // window_seconds}"
        count = await self.client.incr(window_key)
        if count == 1:
            await self.client.expire(window_key, window_seconds)
        remaining = max(0, limit - count)
        reset = ((now // window_seconds) + 1) * window_seconds
        if count > limit:
            raise RateLimitError(retry_after=reset - now)
        return limit, remaining, reset

    async def store_idempotency(
        self,
        *,
        scope_key: str,
        request_fingerprint: str,
        response_body: dict[str, Any],
        status_code: int,
    ) -> dict[str, Any] | None:
        key = f"idempotency:{scope_key}"
        existing = await self.client.get(key)
        if existing:
            data = json.loads(existing)
            if data["fingerprint"] != request_fingerprint:
                raise IdempotencyConflictError()
            return {"body": data["body"], "status_code": data["status_code"]}
        payload = {
            "fingerprint": request_fingerprint,
            "body": response_body,
            "status_code": status_code,
        }
        await self.client.set(key, json.dumps(payload), ex=settings.idempotency_ttl_seconds)
        return None

    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 30) -> str | None:
        token = str(uuid.uuid4())
        acquired = await self.client.set(f"lock:{lock_key}", token, nx=True, ex=ttl_seconds)
        return token if acquired else None

    async def release_lock(self, lock_key: str, token: str) -> None:
        key = f"lock:{lock_key}"
        current = await self.client.get(key)
        if current == token:
            await self.client.delete(key)


redis_service = RedisService()


def request_fingerprint(method: str, path: str, body: bytes) -> str:
    return hashlib.sha256(f"{method}:{path}:{body.decode()}".encode()).hexdigest()
