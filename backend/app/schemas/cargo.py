import uuid
from typing import Any
from datetime import datetime, UTC
from pydantic import BaseModel, Field

class CargoAcceptanceRequest(BaseModel):
    warehouse: str
    booked_pieces: int
    pieces_received: int
    pieces_accepted: int
    rejected_pieces: int = 0
    booked_weight: float
    actual_weight: float
    condition: str = Field(pattern="^(OK|DAMAGED|SHORT)$")
    screening_status: str = Field(pattern="^(SCREENED|X_RAY|NOT_REQUIRED)$")
    screening_method: str | None = None
    damage_notes: str | None = None

class CargoException(BaseModel):
    id: uuid.UUID
    shipment_id: uuid.UUID
    exception_type: str
    severity: str
    details: dict[str, Any]
    status: str = "OPEN"
    created_at: datetime
