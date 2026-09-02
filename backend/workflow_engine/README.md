# Workflow Engine Phase

This directory contains the database-driven state machine workflow engine for FreightCore Backend.

## Components

- **Workflow Models**: `backend/app/db/models/workflow.py` (`StateMachine`, `WorkflowState`, `WorkflowTransition`, `WorkflowInstance`, `WorkflowTransitionHistory`).
- **Workflow Service**: `backend/app/modules/workflow/service.py` (`WorkflowService.transition()`, `GuardRegistry`).
- **Workflow Endpoints**: `backend/app/api/v1/endpoints/workflows.py` (`POST /api/v1/workflows/workflow-instances/{id}/transitions`).

## Quick Usage

```python
from app.modules.workflow.service import WorkflowService, GuardRegistry
```
