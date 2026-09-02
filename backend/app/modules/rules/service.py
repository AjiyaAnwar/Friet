"""Safe declarative rules evaluator."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.models.rules import BusinessRule, BusinessRuleVersion, RuleEvaluationLog


class RuleCondition(BaseModel):
    field: str
    operator: str
    value: Any = None


class RuleConditionGroup(BaseModel):
    combinator: str = "AND"
    conditions: list[RuleCondition | RuleConditionGroup] = Field(default_factory=list)


class RuleAction(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class RuleDefinition(BaseModel):
    conditions: RuleConditionGroup
    actions: list[RuleAction]


ALLOWED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "exists"}
ALLOWED_ACTIONS = {"block", "require_approval", "raise_exception", "notify", "create_task", "set_value"}


class RulesEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def evaluate_conditions(self, group: RuleConditionGroup, context: dict[str, Any]) -> bool:
        results: list[bool] = []
        for item in group.conditions:
            if isinstance(item, RuleConditionGroup):
                results.append(self.evaluate_conditions(item, context))
            else:
                results.append(self._evaluate_condition(item, context))
        if group.combinator == "OR":
            return any(results) if results else False
        if group.combinator == "NOT":
            return not all(results) if results else True
        return all(results) if results else True

    def _evaluate_condition(self, cond: RuleCondition, context: dict[str, Any]) -> bool:
        if cond.operator not in ALLOWED_OPERATORS:
            raise ValidationError(f"Unsupported operator: {cond.operator}")
        value = context.get(cond.field)
        if cond.operator == "eq":
            return value == cond.value
        if cond.operator == "ne":
            return value != cond.value
        if cond.operator == "gt":
            return value is not None and value > cond.value
        if cond.operator == "gte":
            return value is not None and value >= cond.value
        if cond.operator == "lt":
            return value is not None and value < cond.value
        if cond.operator == "lte":
            return value is not None and value <= cond.value
        if cond.operator == "in":
            return value in (cond.value or [])
        if cond.operator == "exists":
            return cond.field in context and context[cond.field] is not None
        return False

    async def evaluate_domain(
        self, tenant_id: Any, domain: str, context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        today = datetime.now(UTC).date()
        result = await self.session.execute(
            select(BusinessRule, BusinessRuleVersion)
            .join(
                BusinessRuleVersion,
                BusinessRule.active_version_id == BusinessRuleVersion.id,
            )
            .where(
                BusinessRule.tenant_id == tenant_id,
                BusinessRule.domain == domain,
                BusinessRule.is_active.is_(True),
            )
            .order_by(BusinessRule.priority)
        )
        actions_out: list[dict[str, Any]] = []
        for rule, version in result.all():
            if rule.active_from and rule.active_from > today:
                continue
            if rule.active_to and rule.active_to < today:
                continue
            definition = RuleDefinition.model_validate(
                {"conditions": version.conditions, "actions": version.actions}
            )
            matched = self.evaluate_conditions(definition.conditions, context)
            log = RuleEvaluationLog(
                business_rule_id=rule.id,
                tenant_id=tenant_id,
                context=context,
                matched=matched,
                result={"actions": [a.model_dump() for a in definition.actions]} if matched else None,
                evaluated_at=datetime.now(UTC),
            )
            self.session.add(log)
            if matched:
                for action in definition.actions:
                    if action.type not in ALLOWED_ACTIONS:
                        raise ValidationError(f"Unsupported action: {action.type}")
                    actions_out.append(action.model_dump())
        return actions_out
