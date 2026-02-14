#!/usr/bin/env python3
"""
Backfill geocoding for existing CFS/MFS/SES incidents that don't have coordinates.

Usage (from host):
    docker compose exec backend python3 scripts/backfill_geocode.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.database import async_session
from app.models.models import Incident, Agency
from app.services.local_geocoder import get_local_geocoder


GEOCODE_AGENCIES = {'CFS', 'MFS', 'SES'}


async def backfill():
    geocoder = get_local_geocoder()
    geocoded = 0
    failed = 0
    skipped = 0

    async with async_session() as db:
        # Find incidents without coordinates from target agencies
        result = await db.execute(
            select(Incident)
            .join(Agency, Incident.agency_id == Agency.id)
            .where(
                Agency.code.in_(GEOCODE_AGENCIES),
                Incident.latitude.is_(None),
            )
            .order_by(Incident.created_at.desc())
        )
        incidents = result.scalars().all()
        print(f"Found {len(incidents)} incidents to geocode")

        for inc in incidents:
            if not inc.address and not inc.suburb:
                skipped += 1
                continue

            try:
                geo = await geocoder.geocode_incident(db, inc)
                if geo:
                    geocoded += 1
                    if geocoded % 20 == 0:
                        print(f"  Geocoded {geocoded}... (last: {inc.address}, {inc.suburb} -> {inc.latitude:.4f},{inc.longitude:.4f})")
                        await db.commit()
                else:
                    failed += 1
                    if failed <= 10:
                        print(f"  No match: {inc.unique_id} - {inc.address}, {inc.suburb}")
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"  Error: {inc.unique_id} - {e}")

        await db.commit()

    print(f"\nBackfill complete: {geocoded} geocoded, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(backfill())
