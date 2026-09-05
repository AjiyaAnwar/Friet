from typing import List, Optional, Dict
from app.schemas.lcl import ConsolidationCreate, ConsolidationResponse
import uuid
from datetime import datetime, timezone

class LCLRepositoryFake:
    def __init__(self):
        self.consolidations: Dict[str, ConsolidationResponse] = {}
        self.mbls = {
            "mbl-1": {"id": "mbl-1", "max_weight": 20000.0, "max_cbm": 30.0, "origin": "CNPVG", "destination": "USLAX", "cost": 5000.0},
            "mbl-2": {"id": "mbl-2", "max_weight": 25000.0, "max_cbm": 60.0, "origin": "CNYTN", "destination": "USLGB", "cost": 8000.0}
        }
        self.hbls = {
            "hbl-1": {"id": "hbl-1", "weight": 5000.0, "cbm": 10.0, "origin": "CNPVG", "destination": "USLAX"},
            "hbl-2": {"id": "hbl-2", "weight": 12000.0, "cbm": 15.0, "origin": "CNPVG", "destination": "USLAX"},
            "hbl-3": {"id": "hbl-3", "weight": 4000.0, "cbm": 5.0, "origin": "CNPVG", "destination": "USLAX"},
            "hbl-4": {"id": "hbl-4", "weight": 10000.0, "cbm": 20.0, "origin": "CNYTN", "destination": "USLGB"}
        }

    def get_pending_hbls(self) -> List[Dict]:
        return list(self.hbls.values())

    def get_available_mbls(self) -> List[Dict]:
        return list(self.mbls.values())

    def create_consolidation(self, data: ConsolidationCreate) -> ConsolidationResponse:
        consolidation_id = str(uuid.uuid4())
        consolidation = ConsolidationResponse(
            id=consolidation_id,
            mbl_id=data.mbl_id,
            hbl_ids=data.hbl_ids,
            created_at=datetime.now(timezone.utc)
        )
        self.consolidations[consolidation_id] = consolidation
        return consolidation

    def get_consolidation(self, consolidation_id: str) -> Optional[ConsolidationResponse]:
        return self.consolidations.get(consolidation_id)

    def get_mbl_cost(self, mbl_id: str) -> float:
        mbl = self.mbls.get(mbl_id)
        return mbl.get("cost", 0.0) if mbl else 0.0

    def get_hbl(self, hbl_id: str) -> Optional[Dict]:
        return self.hbls.get(hbl_id)

lcl_repository = LCLRepositoryFake()
