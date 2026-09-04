"""Exception Management Module (SRS Phase 4.7)."""

from app.modules.exceptions.escalations import evaluate_exception_escalations
from app.modules.exceptions.service import ExceptionService
from app.modules.exceptions.taxonomy import (
    DEFAULT_EXCEPTION_TAXONOMY,
    ExceptionTypeConfig,
    resolve_exception_type,
)

__all__ = [
    "ExceptionService",
    "ExceptionTypeConfig",
    "DEFAULT_EXCEPTION_TAXONOMY",
    "evaluate_exception_escalations",
    "resolve_exception_type",
]

