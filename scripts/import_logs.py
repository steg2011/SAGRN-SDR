#!/usr/bin/env python3
"""
Import historical pager logs into the SAGRN SDR database
Usage: python import_logs.py <log_file_path>
"""

import sys
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.models.database import init_db, async_session
from app.services.parser import MessageParser
from app.services.incident_service import IncidentService


async def import_logs(log_file: str):
    """Import logs from file"""
    print(f"Importing logs from: {log_file}")

    # Initialize database
    await init_db()

    parser = MessageParser()
    incident_service = IncidentService()

    # Ensure agencies exist
    async with async_session() as db:
        await incident_service.ensure_agencies(db)

    # Read and process log file
    processed = 0
    skipped = 0
    errors = 0

    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    total = len(lines)
    print(f"Found {total} lines to process")

    async with async_session() as db:
        for i, line in enumerate(lines):
            try:
                parsed = parser.parse(line)
                if parsed:
                    await incident_service.process_message(db, parsed)
                    processed += 1
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"Error processing line {i}: {e}")

            # Progress update every 1000 lines
            if (i + 1) % 1000 == 0:
                print(f"Progress: {i + 1}/{total} ({processed} processed, {skipped} skipped, {errors} errors)")

    print(f"\nImport complete!")
    print(f"  Processed: {processed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python import_logs.py <log_file_path>")
        sys.exit(1)

    log_file = sys.argv[1]
    if not Path(log_file).exists():
        print(f"Error: File not found: {log_file}")
        sys.exit(1)

    asyncio.run(import_logs(log_file))
