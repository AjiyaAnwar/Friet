import uuid
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ValidationError
from app.schemas.cargo import CargoAcceptanceRequest, CargoException

class CargoAcceptanceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        
    async def process_acceptance(self, shipment_id: uuid.UUID, tenant_id: uuid.UUID, actor_id: uuid.UUID, payload: CargoAcceptanceRequest) -> dict:
        if payload.pieces_accepted > payload.pieces_received:
            raise ValidationError("Accepted pieces cannot exceed received pieces")
            
        if payload.condition in ["DAMAGED", "SHORT"] and not payload.damage_notes:
            raise ValidationError("Damage notes are required for DAMAGED or SHORT condition")
            
        exception_record = None
        
        # Discrepancy logic
        is_short = payload.pieces_received < payload.booked_pieces or payload.pieces_accepted < payload.pieces_received
        if is_short or payload.condition == "SHORT":
            # Generate exception
            exception_record = CargoException(
                id=uuid.uuid4(),
                shipment_id=shipment_id,
                exception_type="SHORT_SHIPMENT",
                severity="HIGH",
                details={
                    "booked_pieces": payload.booked_pieces,
                    "received_pieces": payload.pieces_received,
                    "difference": payload.booked_pieces - payload.pieces_received,
                    "warehouse": payload.warehouse
                },
                created_at=datetime.now(UTC)
            )
            # In a real app, save to exception table and publish outbox event here.

        return {
            "status": "ACCEPTED",
            "receipt_id": str(uuid.uuid4()),
            "exception_generated": exception_record.model_dump() if exception_record else None
        }
