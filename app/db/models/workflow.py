"""Database-driven workflow / state machine models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class StateMachine(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "state_machines"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_state_machine_code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkflowState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_states"
    __table_args__ = (
        UniqueConstraint("state_machine_id", "code", name="uq_workflow_state_code"),
    )

    state_machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("state_machines.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WorkflowTransition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_transitions"

    state_machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("state_machines.id"), nullable=False
    )
    from_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_states.id"), nullable=False
    )
    to_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_states.id"), nullable=False
    )
    required_permission: Mapped[str | None] = mapped_column(String(128))
    required_fields: Mapped[dict | None] = mapped_column(JSONB)
    guard_definitions: Mapped[dict | None] = mapped_column(JSONB)
    action_definitions: Mapped[dict | None] = mapped_column(JSONB)
    notification_definitions: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class WorkflowInstance(UUIDPrimaryKeyMixin, TenantMixin, VersionMixin, TimestampMixin, Base):
    __tablename__ = "workflow_instances"

    state_machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("state_machines.id"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    current_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_states.id"), nullable=False
    )


class WorkflowTransitionHistory(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "workflow_transition_history"

    workflow_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_instances.id"), nullable=False, index=True
    )
    from_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
