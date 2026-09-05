"""Shipment Tracking Event Taxonomy (~60 event types from SRS §15.2)."""

from enum import Enum
from typing import Any


class EventCategory(str, Enum):
    BOOKING = "BOOKING"
    CARGO = "CARGO"
    TRANSPORT = "TRANSPORT"
    CUSTOMS = "CUSTOMS"
    DELIVERY = "DELIVERY"
    EXCEPTION = "EXCEPTION"


class EventSource(str, Enum):
    MANUAL = "MANUAL"
    CARRIER_API = "CARRIER_API"
    AGENT = "AGENT"
    TERMINAL = "TERMINAL"
    SYSTEM = "SYSTEM"


# Complete ~60 Event Type definitions mapped to Category and standard Description
EVENT_TAXONOMY: dict[str, dict[str, Any]] = {
    # -----------------------------------------------------------------------
    # 1. BOOKING
    # -----------------------------------------------------------------------
    "BOOKING_REQUESTED": {"category": EventCategory.BOOKING, "description": "Booking request submitted to carrier"},
    "BOOKING_CONFIRMED": {"category": EventCategory.BOOKING, "description": "Carrier booking confirmed with reference number"},
    "BOOKING_AMENDED": {"category": EventCategory.BOOKING, "description": "Booking details amended with carrier"},
    "BOOKING_CANCELLED": {"category": EventCategory.BOOKING, "description": "Booking cancelled"},
    "BOOKING_ROLLED": {"category": EventCategory.BOOKING, "description": "Booking rolled to subsequent departure / voyage"},
    "CONTAINER_ORDERED": {"category": EventCategory.BOOKING, "description": "Empty equipment ordered from depot"},
    "CONTAINER_RELEASED": {"category": EventCategory.BOOKING, "description": "Equipment release order issued by carrier"},
    "SPACE_CONFIRMED": {"category": EventCategory.BOOKING, "description": "Vessel / flight cargo allocation guaranteed"},
    "SI_SUBMITTED": {"category": EventCategory.BOOKING, "description": "Shipping Instructions filed with carrier"},
    "BOOKING_REJECTED": {"category": EventCategory.BOOKING, "description": "Carrier rejected booking request"},

    # -----------------------------------------------------------------------
    # 2. CARGO
    # -----------------------------------------------------------------------
    "CARGO_READY": {"category": EventCategory.CARGO, "description": "Cargo ready at shipper premises"},
    "CARGO_PICKED_UP": {"category": EventCategory.CARGO, "description": "Cargo picked up from origin address"},
    "CARGO_RECEIVED_ORIGIN": {"category": EventCategory.CARGO, "description": "Cargo received at origin facility / CFS"},
    "CARGO_RECEIVED_CY": {"category": EventCategory.CARGO, "description": "Container received at Container Yard (CY)"},
    "CARGO_STUFFED": {"category": EventCategory.CARGO, "description": "Cargo stuffed and sealed in container"},
    "CARGO_SCREENED": {"category": EventCategory.CARGO, "description": "Aviation security screening passed (X-Ray / ETD)"},
    "CARGO_WAREHOUSE_IN": {"category": EventCategory.CARGO, "description": "Cargo gated into transit warehouse"},
    "CARGO_BUILT_UP": {"category": EventCategory.CARGO, "description": "Air cargo built up into ULD pallet / container"},
    "CARGO_ACCEPTED_AIRLINE": {"category": EventCategory.CARGO, "description": "Cargo accepted at airline cargo terminal"},
    "CARGO_STRIPPED": {"category": EventCategory.CARGO, "description": "Container de-vanned / stripped at destination CFS"},
    "CARGO_STORED": {"category": EventCategory.CARGO, "description": "Cargo placed into bonded storage"},
    "CARGO_BREAKDOWN": {"category": EventCategory.CARGO, "description": "Flight ULD broken down into individual consignments"},

    # -----------------------------------------------------------------------
    # 3. TRANSPORT
    # -----------------------------------------------------------------------
    "GATE_IN": {"category": EventCategory.TRANSPORT, "description": "Container / truck gated in at port or airport terminal"},
    "VGM_SUBMITTED": {"category": EventCategory.TRANSPORT, "description": "Verified Gross Mass submitted to carrier and terminal"},
    "LOADED_ON_VESSEL": {"category": EventCategory.TRANSPORT, "description": "Container loaded on board oceanic vessel"},
    "LOADED_ON_AIRCRAFT": {"category": EventCategory.TRANSPORT, "description": "Cargo loaded on board aircraft"},
    "DEPARTED": {"category": EventCategory.TRANSPORT, "description": "Vessel / aircraft departed origin port / airport"},
    "IN_TRANSIT": {"category": EventCategory.TRANSPORT, "description": "Shipment currently in international transit"},
    "TRANSSHIPPED": {"category": EventCategory.TRANSPORT, "description": "Cargo transshipped at intermediate transshipment hub"},
    "ARRIVED": {"category": EventCategory.TRANSPORT, "description": "Vessel / flight arrived at destination port / airport"},
    "DISCHARGED": {"category": EventCategory.TRANSPORT, "description": "Container / cargo discharged from vessel or aircraft"},
    "GATE_OUT_EMPTY": {"category": EventCategory.TRANSPORT, "description": "Empty container gated out from depot for stuffing"},
    "GATE_OUT_LADEN": {"category": EventCategory.TRANSPORT, "description": "Full container gated out from port for final delivery"},
    "RETURNED_TO_DEPOT": {"category": EventCategory.TRANSPORT, "description": "Empty container returned to carrier depot"},
    "FEEDER_DEPARTED": {"category": EventCategory.TRANSPORT, "description": "Feeder vessel departed origin port"},
    "FEEDER_ARRIVED": {"category": EventCategory.TRANSPORT, "description": "Feeder vessel arrived at transshipment hub"},
    "MBL_ISSUED": {"category": EventCategory.TRANSPORT, "description": "Master Bill of Lading issued by carrier"},
    "HBL_ISSUED": {"category": EventCategory.TRANSPORT, "description": "House Bill of Lading issued to shipper"},
    "MAWB_ISSUED": {"category": EventCategory.TRANSPORT, "description": "Master Air Waybill issued by airline"},
    "HAWB_ISSUED": {"category": EventCategory.TRANSPORT, "description": "House Air Waybill issued to shipper"},

    # -----------------------------------------------------------------------
    # 4. CUSTOMS
    # -----------------------------------------------------------------------
    "DECLARATION_FILED": {"category": EventCategory.CUSTOMS, "description": "Customs export / import declaration filed with authorities"},
    "CUSTOMS_UNDER_EXAMINATION": {"category": EventCategory.CUSTOMS, "description": "Cargo selected for physical or document customs inspection"},
    "CUSTOMS_ASSESSED": {"category": EventCategory.CUSTOMS, "description": "Customs duties and taxes assessed by revenue agency"},
    "DUTY_PAID": {"category": EventCategory.CUSTOMS, "description": "Customs duties and terminal taxes successfully settled"},
    "CUSTOMS_CLEARED": {"category": EventCategory.CUSTOMS, "description": "Customs out-of-charge / formal clearance granted"},
    "CUSTOMS_HELD": {"category": EventCategory.CUSTOMS, "description": "Customs clearance hold placed on shipment"},
    "CUSTOMS_RELEASED": {"category": EventCategory.CUSTOMS, "description": "Customs hold lifted following inspection / compliance review"},
    "SANCTIONS_CHECK_PASSED": {"category": EventCategory.CUSTOMS, "description": "Sanctions screening verified clean across all parties"},
    "SANCTIONS_HELD": {"category": EventCategory.CUSTOMS, "description": "Potential sanctions match flagged for compliance review"},
    "INSPECTION_COMPLETED": {"category": EventCategory.CUSTOMS, "description": "Regulatory inspection (Phyto/Fumigation/DGR) completed"},

    # -----------------------------------------------------------------------
    # 5. DELIVERY
    # -----------------------------------------------------------------------
    "DO_ISSUED": {"category": EventCategory.DELIVERY, "description": "Delivery Order issued to consignee / clearing agent"},
    "OUT_FOR_DELIVERY": {"category": EventCategory.DELIVERY, "description": "Cargo loaded onto delivery truck en route to consignee"},
    "ATTEMPTED_DELIVERY": {"category": EventCategory.DELIVERY, "description": "Delivery attempted at consignee premises"},
    "DELIVERED": {"category": EventCategory.DELIVERY, "description": "Cargo successfully delivered to consignee address"},
    "POD_RECEIVED": {"category": EventCategory.DELIVERY, "description": "Signed Proof of Delivery document received"},
    "POD_CONFIRMED": {"category": EventCategory.DELIVERY, "description": "Proof of Delivery validated and approved"},
    "EMPTY_RETURNED": {"category": EventCategory.DELIVERY, "description": "Empty container returned to designated carrier depot"},
    "DELIVERY_RESCHEDULED": {"category": EventCategory.DELIVERY, "description": "Delivery appointment rescheduled per consignee request"},
    "FINANCIALLY_SETTLED": {"category": EventCategory.DELIVERY, "description": "All job revenue and vendor costs reconciled and posted"},
    "SHIPMENT_CLOSED": {"category": EventCategory.DELIVERY, "description": "Shipment lifecycle completed and archived"},

    # -----------------------------------------------------------------------
    # 6. EXCEPTION
    # -----------------------------------------------------------------------
    "SHIPMENT_DELAY": {"category": EventCategory.EXCEPTION, "description": "Carrier transit or departure delay reported"},
    "VESSEL_ROLL": {"category": EventCategory.EXCEPTION, "description": "Container rolled by shipping line to next scheduled voyage"},
    "CARGO_HOLD": {"category": EventCategory.EXCEPTION, "description": "Operational hold placed on cargo"},
    "MISSING_DOCUMENT": {"category": EventCategory.EXCEPTION, "description": "Mandatory transport or regulatory document missing"},
    "DGR_ISSUE": {"category": EventCategory.EXCEPTION, "description": "Dangerous Goods packaging, labeling, or declaration mismatch"},
    "CARGO_DAMAGE": {"category": EventCategory.EXCEPTION, "description": "Cargo damage discovered and logged with condition survey"},
    "CARGO_LOSS": {"category": EventCategory.EXCEPTION, "description": "Total or partial cargo loss reported"},
    "SHORT_SHIPMENT": {"category": EventCategory.EXCEPTION, "description": "Discrepancy in package count vs booked manifesto"},
    "WRONG_DELIVERY": {"category": EventCategory.EXCEPTION, "description": "Cargo misrouted or delivered to incorrect consignee"},
    "RETURNED_TO_SHIPPER": {"category": EventCategory.EXCEPTION, "description": "Consignment refused by consignee and returned to origin"},
    "SECURITY_HOLD": {"category": EventCategory.EXCEPTION, "description": "Port / airport authority security stop placed on consignment"},
    "WEATHER_DELAY": {"category": EventCategory.EXCEPTION, "description": "Transit delay caused by adverse meteorological conditions"},
    "EQUIPMENT_FAILURE": {"category": EventCategory.EXCEPTION, "description": "Reefer generator or container equipment malfunction"},
}


def validate_event_type(event_type: str) -> tuple[bool, str | None, EventCategory | None]:
    """Validate event type against taxonomy.

    Returns:
        (is_valid, normalized_type, category)
    """
    normalized = event_type.strip().upper()
    if normalized in EVENT_TAXONOMY:
        return True, normalized, EVENT_TAXONOMY[normalized]["category"]
    return False, None, None


def get_category_for_event(event_type: str) -> str:
    """Return category string for an event type or 'TRANSPORT' as fallback."""
    is_valid, normalized, category = validate_event_type(event_type)
    if is_valid and category:
        return category.value
    return EventCategory.TRANSPORT.value

