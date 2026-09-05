from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.schemas.lcl import (
    ConsolidationSuggestion,
    ConsolidationCreate,
    ConsolidationResponse,
    CostAllocationResponse
)
from app.services.lcl_service import LCLService, lcl_service

router = APIRouter()

def get_lcl_service():
    return lcl_service

@router.get("/consolidations/suggestions", response_model=List[ConsolidationSuggestion])
def get_consolidation_suggestions(service: LCLService = Depends(get_lcl_service)):
    return service.generate_suggestions()

@router.post("/consolidations", response_model=ConsolidationResponse)
def create_consolidation(data: ConsolidationCreate, service: LCLService = Depends(get_lcl_service)):
    return service.create_consolidation(data)

@router.get("/consolidations/{id}/cost-allocation", response_model=CostAllocationResponse)
def get_cost_allocation(id: str, service: LCLService = Depends(get_lcl_service)):
    try:
        return service.calculate_cost_allocation(id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
