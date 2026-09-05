import re
from typing import List
from app.schemas.phase6 import TrackingResponse, PODSubmission, PODResponse, AgentJobsResponse, AgentJob
from app.repositories.phase6_repository import Phase6Repository

class Phase6Service:
    def __init__(self, repo: Phase6Repository):
        self.repo = repo

    async def get_tracking_info(self, shipment_id: str) -> TrackingResponse:
        status = await self.repo.get_shipment_status(shipment_id)
        if not status:
            raise ValueError(f"Shipment {shipment_id} not found")
        
        events = await self.repo.get_tracking_events(shipment_id)
        return TrackingResponse(
            shipment_id=shipment_id,
            current_status=status,
            events=events
        )

    async def submit_pod(self, shipment_id: str, pod: PODSubmission) -> PODResponse:
        status = await self.repo.get_shipment_status(shipment_id)
        if not status:
            raise ValueError(f"Shipment {shipment_id} not found")
        
        # Base64 signature validation
        base64_pattern = re.compile(r'^[A-Za-z0-9+/]+={0,2}$')
        if not base64_pattern.match(pod.signature_base64):
            raise ValueError("Invalid signature format")
            
        await self.repo.save_pod(shipment_id, pod.signature_base64, pod.notes, pod.received_by)
        await self.repo.emit_outbox_event("ShipmentDelivered", {"shipment_id": shipment_id, "received_by": pod.received_by})
        
        return PODResponse(
            shipment_id=shipment_id,
            status="Delivered",
            message="POD submitted successfully"
        )

    async def get_my_jobs(self) -> AgentJobsResponse:
        jobs_data = await self.repo.get_agent_jobs()
        
        sorted_jobs = sorted(jobs_data, key=lambda x: x["job_id"])
        
        jobs = [AgentJob(**job) for job in sorted_jobs]
        return AgentJobsResponse(jobs=jobs)
