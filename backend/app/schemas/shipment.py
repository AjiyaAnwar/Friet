import uuid
from typing import Any
from pydantic import BaseModel, Field

class ShipmentTaskInfo(BaseModel):
    task_id: uuid.UUID
    name: str
    status: str
    assigned_to: uuid.UUID | None
    due_date: str | None

class CargoEntryFCL(BaseModel):
    container_no: str
    type: str
    weight: float
    volume: float
    packages_count: int

class CargoEntryAir(BaseModel):
    weight: float
    volume: float
    dimensions: str | None
    packages_count: int

class ShipmentWorkspaceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    booking_id: uuid.UUID
    mode: str
    status: str
    rag_status: str  # RED, AMBER, GREEN
    
    cargo_summary: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[ShipmentTaskInfo] = Field(default_factory=list)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    financials: dict[str, Any] | None = None # Restricted by field-level auth

    model_config = {"from_attributes": True}
