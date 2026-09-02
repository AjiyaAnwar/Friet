"""API v1 route aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    health,
    rules,
    search,
    shipments,
    users,
    workflows,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(shipments.router, prefix="/shipments", tags=["shipments"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
