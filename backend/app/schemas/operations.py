from pydantic import BaseModel
from typing import Any
import uuid
from datetime import datetime

class IdempotencyRecordBase(BaseModel):
    key: str
    response_body: dict[str, Any]
    status_code: int

class DeadLetterRecordBase(BaseModel):
    event_type: str
    payload: dict[str, Any]
    error_message: str

class AWBRecordBase(BaseModel):
    awb_type: str
    airline_prefix: str
    serial_number: str

class SeaShipmentDetailBase(BaseModel):
    mbl_number: str | None = None
    hbl_number: str | None = None
    vessel_name: str | None = None
    voyage_number: str | None = None

class ShipmentExceptionBase(BaseModel):
    exception_type: str
    severity: str
    details: dict[str, Any]

class ULDAssignmentBase(BaseModel):
    uld_number: str
    flight_id: uuid.UUID
    awb_id: uuid.UUID
    pieces: int
    weight: float

class NotificationEventBase(BaseModel):
    event_type: str
    recipient_email: str
    payload: dict[str, Any]
