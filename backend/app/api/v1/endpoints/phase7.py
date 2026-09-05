from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.phase7 import OperationsAnalytics, FinancialAnalytics, DemurrageAnalytics, CarrierPerformanceAnalytics
from app.services.phase7_service import Phase7Service
from app.repositories.phase7_repository import Phase7Repository

router = APIRouter()

def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> Phase7Service:
    return Phase7Service(Phase7Repository(session))

@router.get("/operations", response_model=OperationsAnalytics)
async def get_operations_analytics(service: Phase7Service = Depends(get_service)):
    return await service.get_operations_analytics()

@router.get("/financial", response_model=FinancialAnalytics)
async def get_financial_analytics(service: Phase7Service = Depends(get_service)):
    return await service.get_financial_analytics()

@router.get("/demurrage", response_model=DemurrageAnalytics)
async def get_demurrage_analytics(service: Phase7Service = Depends(get_service)):
    return await service.get_demurrage_analytics()

@router.get("/carrier-performance", response_model=CarrierPerformanceAnalytics)
async def get_carrier_performance_analytics(service: Phase7Service = Depends(get_service)):
    return await service.get_carrier_performance_analytics()
