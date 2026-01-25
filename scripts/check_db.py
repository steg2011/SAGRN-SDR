#!/usr/bin/env python3
"""Check database contents"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from sqlalchemy import select, func
from app.models.database import async_session
from app.models.models import Message, Incident, Agency


async def check_db():
    async with async_session() as db:
        # Count messages
        result = await db.execute(select(func.count(Message.id)))
        msg_count = result.scalar()
        print(f"Messages in database: {msg_count}")

        # Count incidents
        result = await db.execute(select(func.count(Incident.id)))
        inc_count = result.scalar()
        print(f"Incidents in database: {inc_count}")

        # Count agencies
        result = await db.execute(select(Agency))
        agencies = result.scalars().all()
        print(f"\nAgencies: {[a.code for a in agencies]}")

        # Show sample messages
        result = await db.execute(
            select(Message).order_by(Message.id.desc()).limit(5)
        )
        messages = result.scalars().all()
        print(f"\nLast 5 messages:")
        for m in messages:
            print(f"  [{m.timestamp}] agency_id={m.agency_id}, type={m.message_type}, job={m.job_id}")

        # Show sample incidents
        result = await db.execute(
            select(Incident).order_by(Incident.id.desc()).limit(5)
        )
        incidents = result.scalars().all()
        print(f"\nLast 5 incidents:")
        for i in incidents:
            print(f"  [{i.incident_date}] {i.unique_id} - {i.incident_type} - status={i.status}")


if __name__ == '__main__':
    asyncio.run(check_db())
