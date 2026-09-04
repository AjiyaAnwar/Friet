"""Permission codes and RBAC resolution helpers."""

from enum import StrEnum


class SystemRole(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    BRANCH_MANAGER = "BRANCH_MANAGER"
    SALES = "SALES"
    PRICING = "PRICING"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    OPS_SEA = "OPS_SEA"
    OPS_AIR = "OPS_AIR"
    DOCUMENTATION = "DOCUMENTATION"
    COMPLIANCE_DGR = "COMPLIANCE_DGR"
    CUSTOMS = "CUSTOMS"
    FINANCE_AR = "FINANCE_AR"
    FINANCE_AP = "FINANCE_AP"
    FINANCE_CONTROLLER = "FINANCE_CONTROLLER"
    PROCUREMENT = "PROCUREMENT"
    MANAGEMENT = "MANAGEMENT"
    AUDITOR = "AUDITOR"
    CUSTOMER_PORTAL = "CUSTOMER_PORTAL"
    AGENT_PORTAL = "AGENT_PORTAL"
    CARRIER_PORTAL = "CARRIER_PORTAL"


SYSTEM_PERMISSIONS: list[tuple[str, str, str]] = [
    ("user:read", "user", "read"),
    ("user:create", "user", "create"),
    ("user:update", "user", "update"),
    ("role:read", "role", "read"),
    ("role:manage", "role", "manage"),
    ("shipment:read", "shipment", "read"),
    ("shipment:create", "shipment", "create"),
    ("shipment:update", "shipment", "update"),
    ("shipment:transition", "shipment", "transition"),
    ("quotation:read", "quotation", "read"),
    ("quotation:approve", "quotation", "approve"),
    ("rate:create", "rate", "create"),
    ("rate:read", "rate", "read"),
    ("finance:read", "finance", "read"),
    ("finance:create", "finance", "create"),
    ("financial:read", "financial", "read"),
    ("financial:create", "financial", "create"),
    ("financial:approve", "financial", "approve"),
    ("financial:update", "financial", "update"),
    ("invoice:read", "invoice", "read"),
    ("invoice:create", "invoice", "create"),
    ("invoice:approve", "invoice", "approve"),
    ("invoice:send", "invoice", "send"),
    ("payable:read", "payable", "read"),
    ("payable:create", "payable", "create"),
    ("payable:verify", "payable", "verify"),
    ("payable:approve", "payable", "approve"),
    ("payable:pay", "payable", "pay"),
    ("audit:read", "audit", "read"),
    ("workflow:manage", "workflow", "manage"),
    ("rule:manage", "rule", "manage"),
    ("search:read", "search", "read"),
]

PORTAL_ROLES = {SystemRole.CUSTOMER_PORTAL, SystemRole.AGENT_PORTAL, SystemRole.CARRIER_PORTAL}

ROLE_PERMISSION_MAP: dict[SystemRole, set[str]] = {
    SystemRole.SUPER_ADMIN: {p[0] for p in SYSTEM_PERMISSIONS},
    SystemRole.BRANCH_MANAGER: {
        "user:read",
        "user:create",
        "user:update",
        "role:read",
        "shipment:read",
        "shipment:create",
        "shipment:update",
        "shipment:transition",
        "quotation:read",
        "quotation:approve",
        "rate:read",
        "invoice:read",
        "audit:read",
        "search:read",
    },
    SystemRole.SALES: {
        "shipment:read",
        "shipment:create",
        "quotation:read",
        "rate:read",
        "search:read",
    },
    SystemRole.PRICING: {
        "quotation:read",
        "quotation:approve",
        "rate:create",
        "rate:read",
        "search:read",
    },
    SystemRole.CUSTOMER_SERVICE: {
        "shipment:read",
        "quotation:read",
        "invoice:read",
        "search:read",
    },
    SystemRole.FINANCE_CONTROLLER: {
        "finance:read",
        "finance:create",
        "financial:read",
        "financial:create",
        "financial:approve",
        "financial:update",
        "invoice:read",
        "invoice:create",
        "invoice:approve",
        "invoice:send",
        "payable:read",
        "payable:create",
        "payable:verify",
        "payable:approve",
        "payable:pay",
        "audit:read",
        "shipment:read",
        "search:read",
    },
    SystemRole.FINANCE_AR: {
        "finance:read",
        "finance:create",
        "financial:read",
        "financial:create",
        "invoice:read",
        "invoice:create",
        "invoice:approve",
        "invoice:send",
        "shipment:read",
        "search:read",
    },
    SystemRole.FINANCE_AP: {
        "finance:read",
        "finance:create",
        "financial:read",
        "financial:create",
        "invoice:read",
        "payable:read",
        "payable:create",
        "payable:verify",
        "payable:approve",
        "payable:pay",
        "shipment:read",
        "search:read",
    },
    SystemRole.CUSTOMER_PORTAL: {"shipment:read", "quotation:read", "invoice:read", "search:read"},
    SystemRole.AUDITOR: {"audit:read", "shipment:read", "finance:read", "financial:read", "invoice:read", "payable:read"},
}
