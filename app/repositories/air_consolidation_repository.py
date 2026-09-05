from typing import List, Dict, Any
from app.schemas.air_consolidation import HAWB

class AirConsolidationRepositoryFake:
    def __init__(self):
        self.hawbs: List[HAWB] = []
        self.deconsolidations: Dict[str, Any] = {}

    def get_pending_hawbs(self, target_destination: str) -> List[HAWB]:
        return [h for h in self.hawbs if h.destination == target_destination]

    def add_hawb(self, hawb: HAWB):
        self.hawbs.append(hawb)

    def save_deconsolidation_result(self, mawb_id: str, result: dict):
        self.deconsolidations[mawb_id] = result
