import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from app.db.session import async_session_maker
from app.db.models.domain import Shipment, TrackingEvent, CostLine

logger = logging.getLogger(__name__)

async def calculate_daily_accruals():
    """
    Background worker task to calculate daily Demurrage, Detention, and Storage
    accruals for active shipments.
    """
    logger.info("Starting daily accrual calculations for Demurrage/Detention...")
    
    async with async_session_maker() as session:
        # Find shipments that are not CLOSED or DELIVERED
        # In a real scenario, this would look for containers with specific tracking statuses (e.g. at terminal)
        result = await session.execute(
            select(Shipment).where(Shipment.status.notin_(["CLOSED", "DELIVERED"]))
        )
        active_shipments = result.scalars().all()
        
        # Simple placeholder logic for accrual rule evaluation
        base_rate = 50.0  # $50/day standard rate
        
        for shipment in active_shipments:
            # Add a cost line for demurrage
            cost = CostLine(
                shipment_id=shipment.id,
                amount=base_rate,
                vendor_id=None # Accrued to system/terminal
            )
            session.add(cost)
            logger.info(f"Accrued ${base_rate} for shipment {shipment.id}")
            
        await session.commit()
    logger.info("Finished daily accrual calculations.")

if __name__ == "__main__":
    asyncio.run(calculate_daily_accruals())
