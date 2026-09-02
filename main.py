from calculations.lcl_revenue_tons import calculate_lcl_revenue_tons
from calculations.container_utilization import calculate_container_utilization
from fastapi import FastAPI
from pydantic import BaseModel

from calculations.air_freight import Package, calculate_chargeable_weight

app = FastAPI(title="FreightCore Commercial Service")


@app.get("/health")
def health():
    return {"status": "ok"}


class PackageIn(BaseModel):
    gross_weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    quantity: int = 1


class ChargeableWeightRequest(BaseModel):
    packages: list[PackageIn]
    divisor: int = 6000


class ChargeableWeightResponse(BaseModel):
    total_gross_weight_kg: float
    total_volumetric_weight_kg: float
    chargeable_weight_kg: float
    basis: str


@app.post("/api/v1/calculations/air-chargeable-weight", response_model=ChargeableWeightResponse)
def air_chargeable_weight(payload: ChargeableWeightRequest):
    packages = [
        Package(
            gross_weight_kg=p.gross_weight_kg,
            length_cm=p.length_cm,
            width_cm=p.width_cm,
            height_cm=p.height_cm,
            quantity=p.quantity,
        )
        for p in payload.packages
    ]
    result = calculate_chargeable_weight(packages, divisor=payload.divisor)
    return ChargeableWeightResponse(**result.__dict__)

class ContainerUtilizationRequest(BaseModel):
    total_cbm: float
    gross_weight_kg: float
    container_type: str


class ContainerUtilizationResponse(BaseModel):
    container_type: str
    volume_utilization_pct: float
    weight_utilization_pct: float
    effective_utilization_pct: float
    warnings: list[str]
    suggested_container_type: str | None = None


@app.post("/api/v1/calculations/container-utilization", response_model=ContainerUtilizationResponse)
def container_utilization(payload: ContainerUtilizationRequest):
    result = calculate_container_utilization(
        total_cbm=payload.total_cbm,
        gross_weight_kg=payload.gross_weight_kg,
        container_type=payload.container_type,
    )
    return ContainerUtilizationResponse(**result.__dict__)

class LclRevenueTonRequest(BaseModel):
    gross_weight_kg: float
    total_cbm: float
    carrier_minimum_rt: float = 1.0


class LclRevenueTonResponse(BaseModel):
    weight_tons: float
    volume_cbm: float
    revenue_tons: float
    basis: str
    minimum_applied: bool
    billable_revenue_tons: float


@app.post("/api/v1/calculations/lcl-revenue-tons", response_model=LclRevenueTonResponse)
def lcl_revenue_tons(payload: LclRevenueTonRequest):
    result = calculate_lcl_revenue_tons(
        gross_weight_kg=payload.gross_weight_kg,
        total_cbm=payload.total_cbm,
        carrier_minimum_rt=payload.carrier_minimum_rt,
    )
    return LclRevenueTonResponse(**result.__dict__)