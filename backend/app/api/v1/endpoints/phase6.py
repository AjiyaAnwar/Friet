from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.phase6 import TrackingResponse, PODSubmission, PODResponse, AgentJobsResponse
from app.services.phase6_service import Phase6Service
from app.repositories.phase6_repository import Phase6Repository

router = APIRouter()

def get_service(session: Annotated[AsyncSession, Depends(get_db)]) -> Phase6Service:
    return Phase6Service(Phase6Repository(session))

@router.get("/customer-portal/shipments/{id}/tracking", response_model=TrackingResponse)
async def get_tracking(id: str, service: Phase6Service = Depends(get_service)):
    try:
        return await service.get_tracking_info(id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/shipments/{id}/pod", response_model=PODResponse)
async def submit_pod(id: str, pod: PODSubmission, service: Phase6Service = Depends(get_service)):
    try:
        return await service.submit_pod(id, pod)
    except ValueError as e:
        if "format" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/agent-portal/my-jobs", response_model=AgentJobsResponse)
async def get_my_jobs(service: Phase6Service = Depends(get_service)):
    return await service.get_my_jobs()
