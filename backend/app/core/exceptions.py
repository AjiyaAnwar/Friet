"""RFC 7807 problem details and domain exceptions."""

from typing import Any


class FreightCoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        type_slug: str = "internal-error",
        status_code: int = 500,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.type_slug = type_slug
        self.status_code = status_code
        self.errors = errors or []


class NotFoundError(FreightCoreError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, type_slug="not-found", status_code=404)


class UnauthorizedError(FreightCoreError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, type_slug="unauthorized", status_code=401)


class ForbiddenError(FreightCoreError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, type_slug="forbidden", status_code=403)


class ValidationError(FreightCoreError):
    def __init__(
        self,
        message: str = "Validation failed",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, type_slug="validation-error", status_code=422, errors=errors)


class ConflictError(FreightCoreError):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message, type_slug="conflict", status_code=409)


class RateLimitError(FreightCoreError):
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60) -> None:
        super().__init__(message, type_slug="rate-limit", status_code=429)
        self.retry_after = retry_after


class IdempotencyConflictError(FreightCoreError):
    def __init__(self, message: str = "Idempotency key reused with different payload") -> None:
        super().__init__(message, type_slug="idempotency-conflict", status_code=409)


def problem_detail(
    *,
    type_slug: str,
    title: str,
    status: int,
    detail: str,
    instance: str,
    correlation_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"https://freightcore/errors/{type_slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
    }
    if correlation_id:
        body["correlation_id"] = correlation_id
    if errors:
        body["errors"] = errors
    return body
