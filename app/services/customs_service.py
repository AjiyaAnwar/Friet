from app.schemas.customs import CustomsDeclarationCreate, CustomsDeclaration, ClearanceStatus
from app.repositories.customs_repository import CustomsRepository
from decimal import Decimal

# Configurable jurisdictional rules mock
JURISDICTIONAL_RULES = {
    "US": {"max_value_without_review": Decimal("2500.00")},
    "EU": {"max_value_without_review": Decimal("1000.00")}
}

# Mock sanctions list
SANCTIONS_LIST = [
    "WEAPONS",
    "RESTRICTED_TECH"
]

class SanctionsCheckError(Exception):
    pass

class JurisdictionalCheckError(Exception):
    pass

class CustomsService:
    def __init__(self, repository: CustomsRepository):
        self.repository = repository
        
    def _check_sanctions(self, description: str) -> bool:
        """Deterministic sanctions check."""
        description_upper = description.upper()
        for term in SANCTIONS_LIST:
            if term in description_upper:
                return False
        return True
        
    def _check_jurisdictional_rules(self, destination: str, value: Decimal) -> ClearanceStatus:
        """Configurable jurisdictional rules."""
        rules = JURISDICTIONAL_RULES.get(destination)
        if rules and value > rules["max_value_without_review"]:
            return ClearanceStatus.UNDER_REVIEW
        return ClearanceStatus.CLEARED

    def create_declaration(self, shipment_id: str, declaration: CustomsDeclarationCreate) -> CustomsDeclaration:
        # Sanctions check
        if not self._check_sanctions(declaration.description):
            # It's rejected immediately
            created = self.repository.create(shipment_id, declaration)
            return self.repository.update_status(created.id, ClearanceStatus.REJECTED.value)
            
        # Jurisdictional rules check
        initial_status = self._check_jurisdictional_rules(declaration.destination_country, declaration.declared_value)
        
        created = self.repository.create(shipment_id, declaration)
        if initial_status != ClearanceStatus.PENDING:
             created = self.repository.update_status(created.id, initial_status.value)
             
        return created
        
    def get_declaration(self, id: str) -> CustomsDeclaration:
        return self.repository.get(id)

    def update_clearance_status(self, id: str, status: ClearanceStatus) -> CustomsDeclaration:
        return self.repository.update_status(id, status.value)
        
    def sync_sanctions_list(self):
        """Mock structure for the sanctions-list update job."""
        # In a real app, this would fetch from an external API or database and update SANCTIONS_LIST
        pass
