from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class TrackingEvent(BaseModel):
    event_time: datetime
    status: str
    location: str
    description: Optional[str] = None

class TrackingResponse(BaseModel):
    shipment_id: str
    current_status: str
    events: List[TrackingEvent]

class PODSubmission(BaseModel):
    signature_base64: str
    notes: Optional[str] = None
    received_by: str

class PODResponse(BaseModel):
    shipment_id: str
    status: str
    message: str

class AgentJob(BaseModel):
    job_id: str
    shipment_id: str
    pickup_location: str
    delivery_location: str
    status: str
    payout: Decimal

class AgentJobsResponse(BaseModel):
    jobs: List[AgentJob]
