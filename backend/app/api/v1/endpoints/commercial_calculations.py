"""Commercial calculation endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.modules.commercial.service import CommercialService

router = APIRouter()
service = CommercialService()


class AirWeightPackageInput(BaseModel):
    gross_weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    quantity: int = 1


class AirWeightRequest(BaseModel):
    packages: list[AirWeightPackageInput]
    divisor: int = Field(default=6000, gt=0)


class ContainerUtilizationRequest(BaseModel):
    cbm: float
    gross_weight_kg: float
    container_type: str = Field(default="40GP")


class LclRevenueTonsRequest(BaseModel):
    gross_weight_kg: float
    cbm: float
    carrier_minimum_rt: float = Field(default=1.0, ge=0)


@router.post("/calculations/air-chargeable-weight")
async def calculate_air_chargeable_weight(payload: AirWeightRequest) -> dict[str, Any]:
    packages = [p.model_dump() for p in payload.packages]
    result = service.calculate_air_weight(packages, divisor=payload.divisor)
    return result


@router.post("/calculations/container-utilization")
async def calculate_container_utilization_endpoint(
    payload: ContainerUtilizationRequest,
) -> dict[str, Any]:
    result = service.calculate_container(
        cbm=payload.cbm,
        gross_weight_kg=payload.gross_weight_kg,
        container_type=payload.container_type,
    )
    return result


@router.post("/calculations/lcl-revenue-tons")
async def calculate_lcl_revenue_tons_endpoint(
    payload: LclRevenueTonsRequest,
) -> dict[str, Any]:
    result = service.calculate_lcl(
        gross_weight_kg=payload.gross_weight_kg,
        cbm=payload.cbm,
        carrier_minimum_rt=payload.carrier_minimum_rt,
    )
    return result
