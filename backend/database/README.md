# Database Phase

This directory contains the database tier components for FreightCore Backend.

## Components

- **ORM Models**: Located in `backend/app/db/models/` (52 ORM models covering identity, domain, audit, commercial, workflow, rules, SLA, financial, analytics, master reference).
- **Session Management**: Async session factory and context management in `backend/app/db/session.py`.
- **Base & Mixins**: Declarative base and shared mixins (`UUIDPrimaryKeyMixin`, `TimestampMixin`, `TenantMixin`, `AuditActorMixin`, `VersionMixin`) in `backend/app/db/mixins.py`.
- **Database Seed**: Platform seed script in `backend/app/db/seed.py`.
- **Migrations**: Alembic migration scripts located in `backend/alembic/versions/`.

## Quick Usage

```python
from app.db.session import get_db, AsyncSessionLocal
from app.db.seed import seed_platform
```
