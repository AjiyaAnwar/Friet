# Audit Trail Phase

This directory contains the append-only audit logging subsystem for FreightCore Backend.

## Components

- **Audit Log Model**: `backend/app/db/models/audit.py` (`AuditLog` entity storing tenant, actor, branch, entity type/id, action, previous/new value JSONB, correlation ID, IP address, user agent).
- **Audit Service**: `backend/app/modules/audit/service.py` (`AuditService.record()` with automatic sensitive field redaction `redact_payload`).
- **Audit API**: `backend/app/api/v1/endpoints/audit.py` (`GET /api/v1/audit`).

## Quick Usage

```python
from app.modules.audit.service import AuditService, redact_payload
```
