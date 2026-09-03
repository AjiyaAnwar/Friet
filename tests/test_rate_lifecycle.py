"""Lifecycle rules are intentionally unit-tested independently of HTTP."""

import pytest

from app.core.exceptions import ValidationError
from app.modules.commercial.repository import CommercialRepository


@pytest.mark.asyncio
async def test_valid_rate_lifecycle_path():
    repo = CommercialRepository()
    rate = await repo.create_rate({
        "rate_number": "LIFE-1", "rate_type": "AIR", "rate_category": "FAK",
        "carrier_vendor_id": "", "service_name": "STANDARD", "origin_location_id": "O",
        "destination_location_id": "D", "effective_date": "2026-01-01",
        "expiry_date": "2026-12-31", "currency_code": "USD",
    })
    for state in ("PENDING_APPROVAL", "APPROVED", "ACTIVE", "EXPIRED"):
        rate = await repo.transition_rate(rate["id"], state)
        assert rate["status"] == state


@pytest.mark.asyncio
async def test_invalid_rate_lifecycle_path_is_rejected():
    repo = CommercialRepository()
    rate = await repo.create_rate({
        "rate_number": "LIFE-2", "rate_type": "AIR", "rate_category": "FAK",
        "carrier_vendor_id": "", "service_name": "STANDARD", "origin_location_id": "O",
        "destination_location_id": "D", "effective_date": "2026-01-01",
        "expiry_date": "2026-12-31", "currency_code": "USD",
    })
    with pytest.raises(ValidationError):
        await repo.transition_rate(rate["id"], "ACTIVE")
