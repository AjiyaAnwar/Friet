import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

class ULDAllocation(BaseModel):
    awb_id: uuid.UUID
    pieces: int
    weight: float

class ULDCreateRequest(BaseModel):
    uld_number: str
    uld_type: str
    flight_id: uuid.UUID
    max_weight: float
    max_volume: float

class ULDResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    flight_id: uuid.UUID
    uld_number: str
    uld_type: str
    build_status: str = "OPEN"
    build_location: str | None = None
    allocations: list[ULDAllocation] = Field(default_factory=list)
    total_pieces: int = 0
    total_weight: float = 0.0
    
    model_config = {"from_attributes": True}

class FlightManifestResponse(BaseModel):
    flight_id: uuid.UUID
    tenant_id: uuid.UUID
    version: int
    generated_at: datetime
    ulds: list[ULDResponse]
    awbs_loose: list[dict[str, Any]] = Field(default_factory=list)
    total_awbs: int = 0
    total_pieces: int = 0
    total_weight: float = 0.0
