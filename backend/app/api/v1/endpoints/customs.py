from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.schemas.customs import CustomsDeclarationCreate, CustomsDeclaration
from app.services.customs_service import CustomsService
from app.repositories.customs_repository import FakeCustomsRepository

router = APIRouter()

# Dependency mock - usually this would be injected via a Dependency Injector or FastAPI Depends
repo = FakeCustomsRepository()

def get_customs_service():
    return CustomsService(repository=repo)

@router.post("/shipments/{id}/customs-declarations", response_model=CustomsDeclaration, status_code=201)
def create_customs_declaration(
    id: str,
    declaration: CustomsDeclarationCreate,
    service: CustomsService = Depends(get_customs_service)
):
    try:
        return service.create_declaration(id, declaration)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
