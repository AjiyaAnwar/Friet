"""Document Checklist Auto-Generation Rules Engine (SRS Phase 4.4)."""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ChecklistRule:
    rule_id: str
    doc_type_code: str
    doc_name: str
    approval_role: str  # OPERATIONS, COMPLIANCE, CUSTOMS
    is_mandatory: bool
    stage: str  # BOOKING, DEPARTURE, ARRIVAL, CUSTOMS, DELIVERY
    predicate: Callable[[dict[str, Any]], bool]
    description: str = ""


# ---------------------------------------------------------------------------
# Configurable Rule Registry
# ---------------------------------------------------------------------------

DEFAULT_CHECKLIST_RULES: list[ChecklistRule] = [
    # Baseline Sea Freight Documents
    ChecklistRule(
        rule_id="SEA_BASE_BL",
        doc_type_code="BILL_OF_LADING",
        doc_name="Bill of Lading (Original / Seaway)",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: ctx.get("mode", "").upper() == "SEA",
        description="Mandatory transport contract for all sea freight shipments",
    ),
    ChecklistRule(
        rule_id="SEA_FCL_VGM",
        doc_type_code="VGM_CERTIFICATE",
        doc_name="Verified Gross Mass (VGM) Certificate",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: ctx.get("mode", "").upper() == "SEA" and ctx.get("service_type", "").upper() == "FCL",
        description="SOLAS mandatory container weight verification",
    ),
    # Baseline Air Freight Documents
    ChecklistRule(
        rule_id="AIR_BASE_AWB",
        doc_type_code="AIR_WAYBILL",
        doc_name="Air Waybill (MAWB / HAWB)",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: ctx.get("mode", "").upper() == "AIR",
        description="Mandatory transport contract for all air freight shipments",
    ),
    ChecklistRule(
        rule_id="AIR_SCREENING_CERT",
        doc_type_code="SECURITY_SCREENING_CERT",
        doc_name="Aviation Security Screening Certificate",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: ctx.get("mode", "").upper() == "AIR",
        description="Mandatory cargo screening declaration",
    ),
    # Common Commercial & Customs Documents
    ChecklistRule(
        rule_id="COMMERCIAL_INVOICE",
        doc_type_code="COMMERCIAL_INVOICE",
        doc_name="Commercial Invoice",
        approval_role="CUSTOMS",
        is_mandatory=True,
        stage="BOOKING",
        predicate=lambda ctx: True,
        description="Standard commercial invoice for customs and valuation",
    ),
    ChecklistRule(
        rule_id="PACKING_LIST",
        doc_type_code="PACKING_LIST",
        doc_name="Packing List",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="BOOKING",
        predicate=lambda ctx: True,
        description="Detailed itemized packing specification",
    ),
    # Commodity-specific rules: DGR
    ChecklistRule(
        rule_id="DGR_SHIPPER_DECLARATION",
        doc_type_code="DGR_DECLARATION",
        doc_name="Shipper's Declaration for Dangerous Goods",
        approval_role="COMPLIANCE",
        is_mandatory=True,
        stage="BOOKING",
        predicate=lambda ctx: bool(ctx.get("is_dgr") or ctx.get("commodity", "").upper() in {"DGR", "HAZARDOUS", "DANGEROUS"}),
        description="Mandatory IMO/IATA DGR declaration requiring Compliance Officer approval",
    ),
    ChecklistRule(
        rule_id="DGR_EMERGENCY_RESPONSE",
        doc_type_code="DGR_EMERGENCY_RESPONSE",
        doc_name="Material Safety Data Sheet (MSDS) & Emergency Procedures",
        approval_role="COMPLIANCE",
        is_mandatory=True,
        stage="BOOKING",
        predicate=lambda ctx: bool(ctx.get("is_dgr") or ctx.get("commodity", "").upper() in {"DGR", "HAZARDOUS", "DANGEROUS"}),
        description="Safety sheet and handling protocols for hazardous materials",
    ),
    # Commodity-specific rules: Perishable / Food
    ChecklistRule(
        rule_id="PERISHABLE_PHYTOSANITARY",
        doc_type_code="PHYTOSANITARY_CERT",
        doc_name="Phytosanitary / Health Certificate",
        approval_role="CUSTOMS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: bool(
            ctx.get("is_perishable") or ctx.get("commodity", "").upper() in {"PERISHABLE", "FOOD", "AGRICULTURE", "FRUITS", "MEAT"}
        ),
        description="Agricultural and health quarantine certificate",
    ),
    ChecklistRule(
        rule_id="PERISHABLE_TEMP_LOG",
        doc_type_code="TEMPERATURE_DATA_LOG",
        doc_name="Reefer / Cold-Chain Temperature Log",
        approval_role="OPERATIONS",
        is_mandatory=False,
        stage="ARRIVAL",
        predicate=lambda ctx: bool(ctx.get("is_perishable") or ctx.get("temperature_controlled")),
        description="Continuous cold-chain temperature verification",
    ),
    # Letter of Credit (LC) requirements
    ChecklistRule(
        rule_id="LC_CERT_ORIGIN",
        doc_type_code="CERTIFICATE_OF_ORIGIN",
        doc_name="Chamber of Commerce Certificate of Origin",
        approval_role="CUSTOMS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: bool(ctx.get("has_letter_of_credit") or ctx.get("lc_number")),
        description="Country of origin certification required under LC terms",
    ),
    ChecklistRule(
        rule_id="LC_INSPECTION_CERT",
        doc_type_code="INSPECTION_CERTIFICATE",
        doc_name="Pre-Shipment Inspection Certificate",
        approval_role="COMPLIANCE",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: bool(ctx.get("has_letter_of_credit") or ctx.get("lc_number")),
        description="Third-party quality and quantity inspection report",
    ),
    ChecklistRule(
        rule_id="LC_INSURANCE_CERT",
        doc_type_code="MARINE_INSURANCE_CERT",
        doc_name="Marine Cargo Insurance Policy / Certificate",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="BOOKING",
        predicate=lambda ctx: bool(
            ctx.get("has_letter_of_credit")
            or ctx.get("lc_number")
            or ctx.get("incoterm", "").upper() in {"CIF", "CIP"}
        ),
        description="Mandatory cargo insurance coverage certificate",
    ),
    # Destination Jurisdiction Specifics
    ChecklistRule(
        rule_id="DEST_SAUDI_SABER",
        doc_type_code="SABER_SASO_CERTIFICATE",
        doc_name="SABER Conformity Certificate (SASO)",
        approval_role="CUSTOMS",
        is_mandatory=True,
        stage="CUSTOMS",
        predicate=lambda ctx: ctx.get("destination_country", "").upper() in {"SA", "SAU", "SAUDI ARABIA"},
        description="Saudi Customs mandatory product conformity registration",
    ),
    ChecklistRule(
        rule_id="DEST_US_ISF",
        doc_type_code="US_ISF_10_2",
        doc_name="US Customs Importer Security Filing (ISF 10+2)",
        approval_role="CUSTOMS",
        is_mandatory=True,
        stage="DEPARTURE",
        predicate=lambda ctx: ctx.get("destination_country", "").upper() in {"US", "USA", "UNITED STATES"},
        description="Mandatory 24-hour advance filing before loading on vessel",
    ),
    # Delivery stage
    ChecklistRule(
        rule_id="DELIVERY_POD",
        doc_type_code="PROOF_OF_DELIVERY",
        doc_name="Proof of Delivery (Signed POD / Delivery Order)",
        approval_role="OPERATIONS",
        is_mandatory=True,
        stage="DELIVERY",
        predicate=lambda ctx: True,
        description="Consignee signature confirming receipt of cargo",
    ),
]


class DocumentChecklistEngine:
    """Configurable checklist engine evaluating shipment context against rule tables."""

    def __init__(self, rules: list[ChecklistRule] | None = None) -> None:
        self._rules = rules if rules is not None else list(DEFAULT_CHECKLIST_RULES)

    def add_rule(self, rule: ChecklistRule) -> None:
        self._rules.append(rule)

    def generate_checklist(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Evaluate context and generate required checklist items."""
        items: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        for rule in self._rules:
            try:
                if rule.predicate(context):
                    if rule.doc_type_code not in seen_codes:
                        seen_codes.add(rule.doc_type_code)
                        items.append({
                            "rule_id": rule.rule_id,
                            "doc_type_code": rule.doc_type_code,
                            "doc_name": rule.doc_name,
                            "approval_role": rule.approval_role,
                            "is_mandatory": rule.is_mandatory,
                            "stage": rule.stage,
                            "status": "REQUIRED",
                            "description": rule.description,
                        })
            except Exception:
                # Defensive guard against malformed context attributes
                continue

        return items


# Singleton instance
checklist_engine = DocumentChecklistEngine()

