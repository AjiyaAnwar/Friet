"""Business rules endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, require_permission
from app.db.models.rules import BusinessRule, BusinessRuleVersion
from app.db.session import get_db
from app.modules.rules.service import RuleDefinition, RulesEngine

router = APIRouter()


class RuleCreate(BaseModel):
    domain: str
    code: str
    name: str
    priority: int = 100
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]


class RuleEvaluateRequest(BaseModel):
    domain: str
    context: dict[str, Any] = Field(default_factory=dict)


@router.get("")
async def list_rules(
    user: Annotated[CurrentUser, Depends(require_permission("rule:manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await session.execute(
        select(BusinessRule).where(BusinessRule.tenant_id == user.tenant_id)
    )
    data = [
        {"id": str(r.id), "domain": r.domain, "code": r.code, "name": r.name, "is_active": r.is_active}
        for r in result.scalars()
    ]
    return {"data": data, "meta": {"total": len(data)}, "errors": []}


@router.post("")
async def create_rule(
    payload: RuleCreate,
    user: Annotated[CurrentUser, Depends(require_permission("rule:manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    RuleDefinition.model_validate({"conditions": payload.conditions, "actions": payload.actions})
    rule = BusinessRule(
        tenant_id=user.tenant_id,
        domain=payload.domain,
        code=payload.code,
        name=payload.name,
        priority=payload.priority,
        created_by=user.id,
    )
    session.add(rule)
    await session.flush()
    version = BusinessRuleVersion(
        business_rule_id=rule.id,
        version_number=1,
        conditions=payload.conditions,
        actions=payload.actions,
        created_by=user.id,
    )
    session.add(version)
    await session.flush()
    rule.active_version_id = version.id
    await session.commit()
    return {"data": {"id": str(rule.id)}, "meta": {}, "errors": []}


@router.post("/evaluate")
async def evaluate_rules(
    payload: RuleEvaluateRequest,
    user: Annotated[CurrentUser, Depends(require_permission("rule:manage"))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    engine = RulesEngine(session)
    actions = await engine.evaluate_domain(user.tenant_id, payload.domain, payload.context)
    await session.commit()
    return {"data": {"actions": actions}, "meta": {}, "errors": []}
