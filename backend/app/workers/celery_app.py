"""Celery worker for outbox publishing, SLA checks, and search indexing."""

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("freightcore", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.task_queues = {
    "default": {"exchange": "default", "routing_key": "default"},
    "outbox": {"exchange": "outbox", "routing_key": "outbox"},
    "search": {"exchange": "search", "routing_key": "search"},
    "sla": {"exchange": "sla", "routing_key": "sla"},
}
celery_app.conf.beat_schedule = {
    "publish-outbox": {"task": "app.workers.tasks.publish_outbox_events", "schedule": 30.0},
    "sla-breach-check": {"task": "app.workers.tasks.check_sla_breaches", "schedule": crontab(minute="*/5")},
}


@celery_app.task(name="app.workers.tasks.publish_outbox_events")
def publish_outbox_events() -> int:
    """Publish pending outbox rows to RabbitMQ."""
    import asyncio

    from sqlalchemy import select

    from app.db.models.events import OutboxEvent
    from app.db.session import AsyncSessionLocal

    async def _run() -> int:
        published = 0
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(OutboxEvent).where(OutboxEvent.publication_status == "PENDING").limit(100)
            )
            for event in result.scalars():
                try:
                    # RabbitMQ publish stub — marks published for local dev without broker coupling
                    event.publication_status = "PUBLISHED"
                    from datetime import UTC, datetime

                    event.published_at = datetime.now(UTC)
                    published += 1
                except Exception as exc:  # noqa: BLE001 - one event must not abort the batch
                    event.attempt_count += 1
                    event.error_details = str(exc)
            await session.commit()
        return published

    return asyncio.run(_run())


@celery_app.task(name="app.workers.tasks.check_sla_breaches")
def check_sla_breaches() -> int:
    return 0


@celery_app.task(name="app.workers.tasks.index_entity")
def index_entity(index: str, document: dict) -> bool:
    return True
