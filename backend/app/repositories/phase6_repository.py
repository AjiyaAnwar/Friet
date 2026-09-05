import uuid
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models.domain import Shipment, TrackingEvent
from app.db.models.team3_entities import PODRecord, AgentAssignment
from app.db.models.events import OutboxEvent
from app.db.models.commercial import Job

class Phase6Repository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tracking_events(self, shipment_id: str) -> List[Dict[str, Any]]:
        stmt = select(TrackingEvent).where(
            TrackingEvent.shipment_id == uuid.UUID(shipment_id)
        ).order_by(TrackingEvent.event_time.asc())
        result = await self.db.execute(stmt)
        events = result.scalars().all()
        return [
            {
                "event_time": e.event_time,
                "status": e.event_type,
                "location": e.location or "",
                "description": e.description or ""
            }
            for e in events
        ]
    
    async def get_shipment_status(self, shipment_id: str) -> Optional[str]:
        stmt = select(Shipment.status).where(Shipment.id == uuid.UUID(shipment_id))
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_pod(self, shipment_id: str, signature_base64: str, notes: Optional[str], received_by: str):
        pod = PODRecord(
            shipment_id=uuid.UUID(shipment_id),
            signature_url=signature_base64,
            condition=notes or "Received",
            delivery_timestamp=datetime.utcnow().isoformat()
        )
        self.db.add(pod)
        
        stmt = update(Shipment).where(Shipment.id == uuid.UUID(shipment_id)).values(status="Delivered")
        await self.db.execute(stmt)
        await self.db.flush()

    async def emit_outbox_event(self, event_type: str, payload: Dict):
        outbox = OutboxEvent(
            aggregate_type="Shipment",
            aggregate_id=uuid.UUID(payload.get("shipment_id")) if "shipment_id" in payload else uuid.uuid4(),
            event_type=event_type,
            payload=payload
        )
        self.db.add(outbox)
        await self.db.flush()

    async def get_agent_jobs(self) -> List[Dict]:
        stmt = (
            select(AgentAssignment, Job, Shipment)
            .join(Job, AgentAssignment.job_id == Job.id)
            .outerjoin(Shipment, Shipment.job_id == Job.id)
            .order_by(Job.id.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        jobs = []
        for agent_assign, job, shipment in rows:
            jobs.append({
                "job_id": str(job.id),
                "shipment_id": str(shipment.id) if shipment else "",
                "pickup_location": "N/A",
                "delivery_location": "N/A",
                "status": agent_assign.status or "Pending",
                "payout": Decimal("150.00")
            })
        return jobs
