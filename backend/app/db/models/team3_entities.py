"""Team 3 Operations and Finance Entities."""

import uuid
from sqlalchemy import Column, String, Integer, Numeric, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin

class BillOfLading(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bills_of_lading"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    bl_number = Column(String(64))
    bl_type = Column(String(16))
    parent_bl_id = Column(UUID(as_uuid=True), ForeignKey("bills_of_lading.id"), nullable=True)

class VGMRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vgm_records"
    container_id = Column(UUID(as_uuid=True), ForeignKey("containers.id"))
    weight = Column(Numeric(12, 3))
    method = Column(String(16))
    status = Column(String(32))

class DemurrageRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "demurrage_rules"
    carrier_id = Column(UUID(as_uuid=True))
    port_id = Column(UUID(as_uuid=True))
    free_days = Column(Integer)
    daily_rate = Column(Numeric(15, 2))
    currency_code = Column(String(3), ForeignKey("currencies.code"))

class DemurrageAccrual(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "demurrage_accruals"
    container_id = Column(UUID(as_uuid=True), ForeignKey("containers.id"))
    amount = Column(Numeric(15, 2))
    currency_code = Column(String(3), ForeignKey("currencies.code"))
    status = Column(String(32))

class DemurrageOverride(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "demurrage_overrides"
    container_id = Column(UUID(as_uuid=True), ForeignKey("containers.id"))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    new_free_days = Column(Integer)


class CargoAcceptance(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "cargo_acceptances"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    pieces_received = Column(Integer)
    pieces_accepted = Column(Integer)
    condition = Column(String(32))
    screening_status = Column(String(32))

class FlightManifest(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "flight_manifests"
    flight_id = Column(UUID(as_uuid=True), ForeignKey("flight_schedules.id"))
    total_weight = Column(Numeric(12, 3))
    total_volume = Column(Numeric(12, 3))

class SeaConsolidation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sea_consolidations"
    master_bl_id = Column(UUID(as_uuid=True), ForeignKey("bills_of_lading.id"))
    status = Column(String(32))

class AirConsolidation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "air_consolidations"
    master_awb_id = Column(UUID(as_uuid=True), ForeignKey("awb_records.id"))
    status = Column(String(32))

class BreakBulkException(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "break_bulk_exceptions"
    consolidation_id = Column(UUID(as_uuid=True)) # references air or sea
    exception_type = Column(String(64))
    details = Column(String(255))

class CostAllocation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "cost_allocations"
    consolidation_id = Column(UUID(as_uuid=True))
    house_id = Column(UUID(as_uuid=True))
    allocated_amount = Column(Numeric(15, 2))

class Claim(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "claims"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    claim_type = Column(String(32))
    amount = Column(Numeric(15, 2))
    status = Column(String(32))

class CarrierScore(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "carrier_scores"
    carrier_id = Column(UUID(as_uuid=True), ForeignKey("carriers.id"))
    score = Column(Numeric(5, 2))
    period = Column(String(32))

class ReconciliationRun(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "reconciliation_runs"
    run_date = Column(String(32))
    status = Column(String(32))

class PODRecord(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "pod_records"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    delivery_timestamp = Column(String(64))
    condition = Column(String(32))
    signature_url = Column(String(255))

class AgentAssignment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "agent_assignments"
    agent_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    status = Column(String(32))

class ARAgingSnapshot(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ar_aging_snapshots"
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    current_amount = Column(Numeric(15, 2))
    over_30_amount = Column(Numeric(15, 2))
    currency_code = Column(String(3), ForeignKey("currencies.code"))

class ARPayment(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ar_payments"
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    amount = Column(Numeric(15, 2))
    currency_code = Column(String(3), ForeignKey("currencies.code"))

class DGRDeclaration(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dgr_declarations"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    un_number = Column(String(16))
    class_code = Column(String(16))
    status = Column(String(32))

class DGRApproval(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "dgr_approvals"
    declaration_id = Column(UUID(as_uuid=True), ForeignKey("dgr_declarations.id"))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status = Column(String(32))

class CustomsDeclaration(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customs_declarations"
    shipment_id = Column(UUID(as_uuid=True), ForeignKey("shipments.id"))
    hs_code = Column(String(32))
    status = Column(String(32))

class CustomsRule(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customs_rules"
    country_id = Column(UUID(as_uuid=True), ForeignKey("countries.id"))
    rule_type = Column(String(64))
    details = Column(JSON)

class SanctionsListVersion(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sanctions_list_versions"
    version_id = Column(String(64))
    active = Column(Boolean)

class DocumentApproval(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "document_approvals"
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    status = Column(String(32))
