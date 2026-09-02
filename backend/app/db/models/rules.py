"""Versioned configurable business rules models."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import (
    AuditActorMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class BusinessRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "business_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "domain", "code", name="uq_rule_domain_code"),)

    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active_from: Mapped[date | None] = mapped_column(Date)
    active_to: Mapped[date | None] = mapped_column(Date)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BusinessRuleVersion(UUIDPrimaryKeyMixin, TimestampMixin, AuditActorMixin, Base):
    __tablename__ = "business_rule_versions"
    __table_args__ = (
        UniqueConstraint("business_rule_id", "version_number", name="uq_rule_version"),
    )

    business_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_rules.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class RuleEvaluationLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rule_evaluation_logs"

    business_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_rules.id"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
