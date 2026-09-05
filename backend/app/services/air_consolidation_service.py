from typing import List
from decimal import Decimal
from app.schemas.air_consolidation import PlanningSuggestion, DeconsolidationRequest, DeconsolidationResult
from app.repositories.air_consolidation_repository import AirConsolidationRepository

class AirConsolidationService:
    def __init__(self, repo: AirConsolidationRepository):
        self.repo = repo

    def calculate_volumetric_weight(self, volume: Decimal) -> Decimal:
        return volume * Decimal("167.0")

    async def get_planning_suggestions(self, target_destination: str, max_weight: Decimal, max_volume: Decimal) -> PlanningSuggestion:
        hawbs = await self.repo.get_pending_hawbs(target_destination)
        
        selected_hawbs = []
        tot_actual_weight = Decimal("0")
        tot_volume = Decimal("0")
        
        for h in hawbs:
            actual_weight = Decimal("100") # Mock weight
            volume = Decimal("10") # Mock volume
            if tot_actual_weight + actual_weight <= max_weight and tot_volume + volume <= max_volume:
                selected_hawbs.append(str(h.id))
                tot_actual_weight += actual_weight
                tot_volume += volume
                
        tot_volumetric_weight = self.calculate_volumetric_weight(tot_volume)
        tot_chargeable_weight = max(tot_actual_weight, tot_volumetric_weight)
        
        wt_pct = (tot_actual_weight / max_weight * Decimal("100")) if max_weight > 0 else Decimal("0")
        vol_pct = (tot_volume / max_volume * Decimal("100")) if max_volume > 0 else Decimal("0")
        
        return PlanningSuggestion(
            suggested_hawbs=selected_hawbs,
            total_actual_weight=tot_actual_weight,
            total_volume=tot_volume,
            total_volumetric_weight=tot_volumetric_weight,
            total_chargeable_weight=tot_chargeable_weight,
            utilization_weight_pct=wt_pct,
            utilization_volume_pct=vol_pct
        )

    async def deconsolidate(self, req: DeconsolidationRequest) -> DeconsolidationResult:
        exceptions = 0
        for item in req.items:
            if item.condition != "good" or item.discrepancy_notes is not None:
                exceptions += 1
                
        status = "completed_with_exceptions" if exceptions > 0 else "completed"
        
        result = DeconsolidationResult(
            mawb_id=req.mawb_id,
            status=status,
            exceptions_raised=exceptions,
            processed_items=len(req.items)
        )
        
        await self.repo.save_deconsolidation_result(req.mawb_id, result.model_dump() if hasattr(result, "model_dump") else result.dict())
        return result
