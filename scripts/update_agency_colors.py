#!/usr/bin/env python3
"""
Script to update agency colors in the database.
Run this after changing AGENCY_CONFIG colors in incident_service.py
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select
from app.models.database import async_session
from app.models.models import Agency
from app.services.incident_service import IncidentService


async def update_agency_colors():
    """Update all agency colors from AGENCY_CONFIG"""
    service = IncidentService()

    async with async_session() as db:
        for code, config in service.AGENCY_CONFIG.items():
            result = await db.execute(
                select(Agency).where(Agency.code == code)
            )
            agency = result.scalar_one_or_none()

            if agency:
                old_color = agency.color
                agency.color = config['color']
                print(f"Updated {code}: {old_color} -> {config['color']}")
            else:
                print(f"Agency {code} not found in database")

        await db.commit()
        print("\nDone!")


if __name__ == "__main__":
    asyncio.run(update_agency_colors())
