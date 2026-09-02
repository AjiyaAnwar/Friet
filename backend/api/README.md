# API Phase

This directory contains the API router, HTTP middleware pipeline, and endpoint controllers for FreightCore Backend.

## Components

- **Application Entrypoint**: `backend/app/main.py` (FastAPI app, lifespan manager, exception handlers, health checks, Prometheus metrics).
- **API V1 Router**: `backend/app/api/v1/router.py` aggregating endpoint routers.
- **Endpoints**:
  - `/auth`: Login, logout, refresh, me, MFA (`auth.py`).
  - `/users`: User management & tenant user lookups (`users.py`).
  - `/shipments`: Shipment creation, listing, transitions (`shipments.py`).
  - `/workflows`: State machine instances & transitions (`workflows.py`).
  - `/rules`: Business rule registration & evaluation (`rules.py`).
  - `/audit`: Audit log search (`audit.py`).
  - `/search`: Global search across indices (`search.py`).
  - `/health`: Liveness & readiness probes (`health.py`).
- **HTTP Middleware**: `backend/app/middleware/http.py` (Correlation ID, Request size limit, Redis rate limiting, Idempotency key handling).

## Quick Usage

```python
from app.main import app
from app.api.dependencies import get_current_user, require_permission
```
