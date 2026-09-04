"""API v1 route aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    audit,
    auth,
    commercial_calculations,
    commercial_master_data,
    commercial_parties,
    commercial_quotations,
    commercial_rates,
    commercial_rfqs,
    commercial_routes,
    commercial_schedules,
    documents,
    eta,
    exceptions,
    financial,
    health,
    rules,
    search,
    shipments,
    tracking,
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
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(tracking.router, tags=["tracking"])
api_router.include_router(eta.router, tags=["eta-history"])
api_router.include_router(exceptions.router, tags=["exceptions"])
api_router.include_router(search.router, prefix="/search", tags=["search"])

# Commercial Master Data, Rates, Calculations, RFQs, and Quotations
# Exposed directly under /api/v1 (e.g. /api/v1/admin/countries, /api/v1/rates)
api_router.include_router(commercial_master_data.router, tags=["commercial-master-data"])
api_router.include_router(commercial_parties.router, tags=["commercial-parties"])
api_router.include_router(commercial_rates.router, tags=["commercial-rates"])
api_router.include_router(commercial_calculations.router, tags=["commercial-calculations"])
api_router.include_router(commercial_rfqs.router, tags=["commercial-rfqs"])
api_router.include_router(commercial_routes.router, tags=["commercial-routes"])
api_router.include_router(commercial_schedules.router, tags=["commercial-schedules"])
api_router.include_router(commercial_quotations.router, tags=["commercial-quotations"])

# Commercial Financial Integrity (Phase 5) and Commercial Analytics (Phase 7)
api_router.include_router(financial.router, tags=["commercial-financial"])
api_router.include_router(analytics.router, tags=["commercial-analytics"])

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
