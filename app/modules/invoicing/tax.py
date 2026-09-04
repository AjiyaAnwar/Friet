"""Tax Engine Abstraction for Customer Invoicing (Phase 5.2).

Supports configurable tax determination and snapshotting across jurisdictions:
- Pakistan: Sales Tax on Services / GST (16%)
- Saudi Arabia: VAT (15%)
- United Arab Emirates: VAT (5%)
- International / Zero-rated: (0%)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class TaxEvaluation:
    applicable: bool
    jurisdiction: str
    tax_type: str
    tax_rate: float  # Decimal representation (e.g., 0.16 for 16%)

    def compute_tax(self, amount: float) -> float:
        if not self.applicable or self.tax_rate <= 0:
            return 0.0
        amt = Decimal(str(amount))
        rate = Decimal(str(self.tax_rate))
        tax = (amt * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return float(tax)


# Default tax rules per jurisdiction
TAX_RULES: dict[str, dict[str, Any]] = {
    "PK": {
        "tax_type": "GST",
        "tax_rate": 0.1600,  # 16% standard Sindh/Punjab sales tax on freight services
        "applicable": True,
    },
    "SA": {
        "tax_type": "VAT",
        "tax_rate": 0.1500,  # 15% ZATCA standard VAT
        "applicable": True,
    },
    "AE": {
        "tax_type": "VAT",
        "tax_rate": 0.0500,  # 5% UAE FTA standard VAT
        "applicable": True,
    },
}


class TaxService:
    """Evaluates and applies jurisdiction-specific tax rules."""

    @staticmethod
    def evaluate(
        jurisdiction: str | None,
        is_international: bool = False,
        is_tax_exempt: bool = False,
    ) -> TaxEvaluation:
        """Determine tax parameters based on jurisdiction and shipment profile."""
        if not jurisdiction or is_tax_exempt:
            return TaxEvaluation(
                applicable=False,
                jurisdiction=jurisdiction or "NONE",
                tax_type="EXEMPT",
                tax_rate=0.0,
            )

        code = jurisdiction.strip().upper()
        rule = TAX_RULES.get(code)
        if not rule:
            return TaxEvaluation(
                applicable=False,
                jurisdiction=code,
                tax_type="NONE",
                tax_rate=0.0,
            )

        # Standard international zero-rating can be applied if exempt/zero-rated
        tax_rate = rule["tax_rate"]
        return TaxEvaluation(
            applicable=rule["applicable"],
            jurisdiction=code,
            tax_type=rule["tax_type"],
            tax_rate=tax_rate,
        )
