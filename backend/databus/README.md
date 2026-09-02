# Data Bus & Background Workers Phase

This directory contains the event databus, transactional outbox pattern, and Celery background workers for FreightCore Backend.

## Components

- **Outbox Models**: `backend/app/db/models/events.py` (`OutboxEvent`, `ProcessedEvent`).
- **Outbox Service**: `backend/app/modules/events/service.py` (`OutboxService.enqueue()`).
- **Celery Worker Tasks**: `backend/app/workers/celery_app.py` (Outbox event publisher task, SLA breach monitor task, search indexer task).

## Quick Usage

```python
from app.modules.events.service import OutboxService
from app.workers.celery_app import celery_app
```
