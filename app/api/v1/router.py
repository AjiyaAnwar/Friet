"""API v1 route aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    commercial_calculations,
    commercial_master_data,
    commercial_quotations,
    commercial_rates,
    commercial_rfqs,
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

# Commercial Master Data, Rates, Calculations, RFQs, and Quotations
# Exposed directly under /api/v1 (e.g. /api/v1/admin/countries, /api/v1/rates)
api_router.include_router(commercial_master_data.router, tags=["commercial-master-data"])
api_router.include_router(commercial_rates.router, tags=["commercial-rates"])
api_router.include_router(commercial_calculations.router, tags=["commercial-calculations"])
api_router.include_router(commercial_rfqs.router, tags=["commercial-rfqs"])
api_router.include_router(commercial_quotations.router, tags=["commercial-quotations"])

# Also alias under /commercial for backward compatibility
api_router.include_router(
    commercial_master_data.router,
    prefix="/commercial",
    tags=["commercial-master-data"],
    include_in_schema=False,
)
api_router.include_router(
    commercial_rates.router,
    prefix="/commercial",
    tags=["commercial-rates"],
    include_in_schema=False,
)
api_router.include_router(
    commercial_calculations.router,
    prefix="/commercial",
    tags=["commercial-calculations"],
    include_in_schema=False,
)