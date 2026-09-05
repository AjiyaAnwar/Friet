from typing import List, Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from app.schemas.lcl import (
    ConsolidationSuggestion,
    ConsolidationCreate,
    ConsolidationResponse,
    CostAllocationResponse,
    HBLCostAllocation
)
from app.repositories.lcl_repository import lcl_repository

def get_chargeable_weight(weight: Decimal, cbm: Decimal) -> Decimal:
    # Standard LCL assumption: 1 CBM = 1000 KG
    return max(weight, cbm * Decimal('1000'))

class LCLService:
    def __init__(self, repo=lcl_repository):
        self.repo = repo

    def generate_suggestions(self) -> List[ConsolidationSuggestion]:
        mbls = self.repo.get_available_mbls()
        hbls = self.repo.get_pending_hbls()
        
        # Deterministic sorting
        mbls_sorted = sorted(mbls, key=lambda x: x['id'])
        hbls_sorted = sorted(hbls, key=lambda x: x['id'])
        
        suggestions = []
        
        for mbl in mbls_sorted:
            max_weight = Decimal(str(mbl['max_weight']))
            max_cbm = Decimal(str(mbl['max_cbm']))
            
            matching_hbls = [
                h for h in hbls_sorted 
                if h['origin'] == mbl['origin'] and h['destination'] == mbl['destination']
            ]
            
            selected_hbls = []
            total_weight = Decimal('0')
            total_cbm = Decimal('0')
            
            for hbl in matching_hbls:
                h_weight = Decimal(str(hbl['weight']))
                h_cbm = Decimal(str(hbl['cbm']))
                
                if total_weight + h_weight <= max_weight and total_cbm + h_cbm <= max_cbm:
                    selected_hbls.append(hbl['id'])
                    total_weight += h_weight
                    total_cbm += h_cbm
            
            if selected_hbls:
                weight_util = (total_weight / max_weight * Decimal('100')) if max_weight > 0 else Decimal('0')
                cbm_util = (total_cbm / max_cbm * Decimal('100')) if max_cbm > 0 else Decimal('0')
                
                suggestions.append(ConsolidationSuggestion(
                    mbl_id=mbl['id'],
                    hbl_ids=selected_hbls,
                    total_weight=total_weight.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    total_cbm=total_cbm.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    weight_utilization=weight_util.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                    cbm_utilization=cbm_util.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                ))
                
        return suggestions

    def create_consolidation(self, data: ConsolidationCreate) -> ConsolidationResponse:
        return self.repo.create_consolidation(data)

    def calculate_cost_allocation(self, consolidation_id: str) -> CostAllocationResponse:
        consolidation = self.repo.get_consolidation(consolidation_id)
        if not consolidation:
            raise ValueError("Consolidation not found")
            
        mbl_cost = Decimal(str(self.repo.get_mbl_cost(consolidation.mbl_id)))
        
        hbl_details = []
        total_chargeable_weight = Decimal('0')
        
        for hbl_id in consolidation.hbl_ids:
            hbl = self.repo.get_hbl(hbl_id)
            if hbl:
                weight = Decimal(str(hbl['weight']))
                cbm = Decimal(str(hbl['cbm']))
                cw = get_chargeable_weight(weight, cbm)
                hbl_details.append((hbl_id, cw))
                total_chargeable_weight += cw
                
        allocations = []
        allocated_total = Decimal('0')
        
        for i, (hbl_id, cw) in enumerate(hbl_details):
            if i == len(hbl_details) - 1:
                # Last item takes the remainder to ensure deterministic rounding matches total
                cost = mbl_cost - allocated_total
            else:
                ratio = cw / total_chargeable_weight if total_chargeable_weight > 0 else Decimal('0')
                cost = (mbl_cost * ratio).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                allocated_total += cost
                
            allocations.append(HBLCostAllocation(hbl_id=hbl_id, allocated_cost=cost))
            
        return CostAllocationResponse(
            consolidation_id=consolidation_id,
            total_cost=mbl_cost,
            allocations=allocations
        )

lcl_service = LCLService()
