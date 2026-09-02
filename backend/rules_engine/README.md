# Rules Engine Phase

This directory contains the safe, declarative rules evaluation engine for FreightCore Backend.

## Components

- **Rules Models**: `backend/app/db/models/rules.py` (`BusinessRule`, `BusinessRuleVersion`, `RuleEvaluationLog`).
- **Rules Engine Service**: `backend/app/modules/rules/service.py` (`RulesEngine` with `AND`/`OR`/`NOT` condition groups and operators `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `exists`).
- **Rules Endpoints**: `backend/app/api/v1/endpoints/rules.py` (`POST /api/v1/rules`, `POST /api/v1/rules/evaluate`).

## Quick Usage

```python
from app.modules.rules.service import RulesEngine, RuleConditionGroup, RuleCondition
```
