from typing import Protocol, List, Optional
from app.schemas.customs import CustomsDeclaration, CustomsDeclarationCreate
from datetime import datetime, timezone
import uuid

class CustomsRepository(Protocol):
    def create(self, shipment_id: str, declaration: CustomsDeclarationCreate) -> CustomsDeclaration:
        ...
        
    def get(self, id: str) -> Optional[CustomsDeclaration]:
        ...
        
    def list_by_shipment(self, shipment_id: str) -> List[CustomsDeclaration]:
        ...
        
    def update_status(self, id: str, status: str) -> Optional[CustomsDeclaration]:
        ...

class FakeCustomsRepository:
    def __init__(self):
        self.declarations = {}
        
    def create(self, shipment_id: str, declaration: CustomsDeclarationCreate) -> CustomsDeclaration:
        now = datetime.now(timezone.utc)
        declaration_id = str(uuid.uuid4())
        record = CustomsDeclaration(
            id=declaration_id,
            shipment_id=shipment_id,
            status="PENDING",
            created_at=now,
            updated_at=now,
            **declaration.model_dump()
        )
        self.declarations[declaration_id] = record
        return record
        
    def get(self, id: str) -> Optional[CustomsDeclaration]:
        return self.declarations.get(id)
        
    def list_by_shipment(self, shipment_id: str) -> List[CustomsDeclaration]:
        return [d for d in self.declarations.values() if d.shipment_id == shipment_id]
        
    def update_status(self, id: str, status: str) -> Optional[CustomsDeclaration]:
        if id in self.declarations:
            record = self.declarations[id]
            # Create a new instance to simulate DB update
            update_data = record.model_dump()
            update_data['status'] = status
            update_data['updated_at'] = datetime.now(timezone.utc)
            updated_record = CustomsDeclaration(**update_data)
            self.declarations[id] = updated_record
            return updated_record
        return None
