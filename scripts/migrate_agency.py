#!/usr/bin/env python3
"""
Migration script to update agency assignments for existing messages and incidents.
Re-parses all messages and updates their agency_id based on the new detection logic.
Also updates incidents based on their linked messages.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import sqlite3
from app.services.parser import MessageParser


def get_agency_id(cursor, agency_code: str) -> int:
    """Get agency ID from code, or return UNKNOWN agency ID."""
    cursor.execute('SELECT id FROM agencies WHERE code = ?', (agency_code,))
    result = cursor.fetchone()
    if result:
        return result[0]
    # Return UNKNOWN agency ID
    cursor.execute('SELECT id FROM agencies WHERE code = ?', ('UNKNOWN',))
    return cursor.fetchone()[0]


def migrate_messages(cursor, parser, agency_ids, dry_run: bool = False):
    """Re-parse all messages and update agency assignments."""

    # Get current counts
    cursor.execute('''
        SELECT a.code, COUNT(*)
        FROM messages m
        LEFT JOIN agencies a ON m.agency_id = a.id
        GROUP BY a.code
    ''')
    print("=== MESSAGES BEFORE MIGRATION ===")
    for code, count in cursor.fetchall():
        print(f"  {code}: {count}")
    print()

    # Get all messages
    cursor.execute('SELECT id, raw_message, agency_id FROM messages')
    messages = cursor.fetchall()

    updates = []
    changes = {'MFS': 0, 'CFS': 0, 'SES': 0, 'SAAS': 0, 'MedStar': 0, 'UNKNOWN': 0}

    for msg_id, raw_message, current_agency_id in messages:
        parsed = parser.parse(raw_message)
        if not parsed:
            continue

        new_agency = parsed.agency or 'UNKNOWN'
        new_agency_id = agency_ids.get(new_agency, agency_ids['UNKNOWN'])

        if new_agency_id != current_agency_id:
            updates.append((new_agency_id, msg_id))
            changes[new_agency] = changes.get(new_agency, 0) + 1

    print(f"=== MESSAGE CHANGES TO APPLY ===")
    print(f"  Total messages: {len(messages)}")
    print(f"  Messages to update: {len(updates)}")
    print()
    print("  Changes by new agency:")
    for agency, count in sorted(changes.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"    {agency}: {count}")
    print()

    if not dry_run:
        cursor.executemany('UPDATE messages SET agency_id = ? WHERE id = ?', updates)
        print(f"Updated {len(updates)} messages")

    return updates


def migrate_incidents(cursor, parser, agency_ids, dry_run: bool = False):
    """Update incidents and create missing incidents for SES/CFS messages."""
    from datetime import datetime

    # Get current incident counts
    cursor.execute('''
        SELECT a.code, COUNT(*)
        FROM incidents i
        LEFT JOIN agencies a ON i.agency_id = a.id
        GROUP BY a.code
    ''')
    print("=== INCIDENTS BEFORE MIGRATION ===")
    for code, count in cursor.fetchall():
        print(f"  {code}: {count}")
    print()

    # Update existing incidents based on their messages
    cursor.execute('''
        SELECT i.id, i.incident_number, i.agency_id, m.raw_message
        FROM incidents i
        LEFT JOIN messages m ON m.incident_id = i.id
        WHERE m.raw_message IS NOT NULL
        GROUP BY i.id
    ''')
    incidents = cursor.fetchall()

    updates = []
    changes = {'MFS': 0, 'CFS': 0, 'SES': 0}

    for inc_id, incident_number, current_agency_id, raw_message in incidents:
        new_agency = None

        # Check incident number format - S prefix means SES
        if incident_number and incident_number.startswith('S'):
            new_agency = 'SES'
        elif raw_message:
            parsed = parser.parse(raw_message)
            if parsed and parsed.agency in ('MFS', 'CFS', 'SES'):
                new_agency = parsed.agency

        if new_agency:
            new_agency_id = agency_ids.get(new_agency)
            if new_agency_id and new_agency_id != current_agency_id:
                updates.append((new_agency_id, inc_id))
                changes[new_agency] = changes.get(new_agency, 0) + 1

    print(f"=== EXISTING INCIDENT UPDATES ===")
    print(f"  Incidents to update: {len(updates)}")
    for agency, count in sorted(changes.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"    {agency}: {count}")
    print()

    # Find messages without incidents that should have incidents
    # Re-parse to determine if they're actually dispatch messages
    cursor.execute('''
        SELECT m.id, m.raw_message, m.timestamp, a.code
        FROM messages m
        LEFT JOIN agencies a ON m.agency_id = a.id
        WHERE m.incident_id IS NULL
        AND a.code IN ('SES', 'CFS', 'MFS')
    ''')
    orphan_messages = cursor.fetchall()

    new_incidents = []
    incident_links = []  # (incident_id, message_id)
    pending_incidents = {}  # Track unique_ids being created: unique_id -> [msg_ids]

    message_type_updates = []  # Messages that need message_type updated to 'dispatch'

    for msg_id, raw_message, timestamp, agency_code in orphan_messages:
        parsed = parser.parse(raw_message)
        # Only process actual dispatch messages with incident numbers
        if not parsed or not parsed.incident_number or parsed.message_type != 'dispatch':
            continue

        # Track that this message should be a dispatch
        message_type_updates.append(msg_id)

        # Generate unique_id
        try:
            ts = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f') if isinstance(timestamp, str) else timestamp
        except ValueError:
            ts = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S') if isinstance(timestamp, str) else timestamp

        date_str = ts.strftime('%Y%m%d')
        inc_num = parsed.incident_number.upper().replace(':', '').replace(' ', '')
        unique_id = f"{parsed.agency}_{inc_num}_{date_str}"

        # Check if incident already exists (by unique_id or by incident_number + date)
        cursor.execute('SELECT id FROM incidents WHERE unique_id = ?', (unique_id,))
        existing = cursor.fetchone()

        if not existing:
            # Also check by incident number and date (might exist with different agency prefix)
            cursor.execute('''
                SELECT id FROM incidents
                WHERE incident_number = ? AND date(incident_date) = date(?)
            ''', (parsed.incident_number, timestamp))
            existing = cursor.fetchone()

        if existing:
            # Link message to existing incident
            incident_links.append((existing[0], msg_id))
        elif unique_id in pending_incidents:
            # Already planning to create this incident, just track the message
            pending_incidents[unique_id]['msg_ids'].append(msg_id)
        else:
            # Create new incident
            agency_id = agency_ids.get(parsed.agency, agency_ids['UNKNOWN'])
            pending_incidents[unique_id] = {
                'data': (
                    unique_id,
                    agency_id,
                    parsed.incident_number,
                    timestamp,
                    parsed.incident_type,
                    parsed.alarm_level,
                    parsed.location_text,
                    parsed.suburb,
                    parsed.map_reference,
                    'active',
                    timestamp,
                    timestamp,
                ),
                'msg_ids': [msg_id]
            }

    # Convert pending_incidents to list format
    new_incidents = list(pending_incidents.values())

    print(f"=== NEW INCIDENTS TO CREATE ===")
    print(f"  Orphan messages checked: {len(orphan_messages)}")
    print(f"  Messages needing type update: {len(message_type_updates)}")
    print(f"  New incidents to create: {len(new_incidents)}")
    print(f"  Messages to link to existing: {len(incident_links)}")
    print()

    if not dry_run:
        # Apply updates to existing incidents
        cursor.executemany('UPDATE incidents SET agency_id = ? WHERE id = ?', updates)
        print(f"Updated {len(updates)} existing incidents")

        # Create new incidents
        for inc_info in new_incidents:
            inc_data = inc_info['data']
            msg_ids = inc_info['msg_ids']
            cursor.execute('''
                INSERT INTO incidents (unique_id, agency_id, incident_number, incident_date,
                    incident_type, alarm_level, address, suburb, map_reference, status,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', inc_data)
            incident_id = cursor.lastrowid
            # Link all messages for this incident
            for msg_id in msg_ids:
                cursor.execute('UPDATE messages SET incident_id = ? WHERE id = ?', (incident_id, msg_id))

        print(f"Created {len(new_incidents)} new incidents")

        # Link messages to existing incidents
        for incident_id, msg_id in incident_links:
            cursor.execute('UPDATE messages SET incident_id = ? WHERE id = ?', (incident_id, msg_id))
        print(f"Linked {len(incident_links)} messages to existing incidents")

        # Update message_type for dispatch messages
        for msg_id in message_type_updates:
            cursor.execute("UPDATE messages SET message_type = 'dispatch' WHERE id = ?", (msg_id,))
        print(f"Updated message_type for {len(message_type_updates)} messages")

    return updates, new_incidents, incident_links


def migrate_agencies(db_path: str, dry_run: bool = False):
    """Re-parse all messages and incidents, updating agency assignments."""

    parser = MessageParser()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get agency IDs
    agency_ids = {}
    cursor.execute('SELECT code, id FROM agencies')
    for code, id in cursor.fetchall():
        agency_ids[code] = id

    print(f"Agency IDs: {agency_ids}")
    print()

    # Migrate messages
    print("=" * 50)
    print("MIGRATING MESSAGES")
    print("=" * 50)
    migrate_messages(cursor, parser, agency_ids, dry_run)
    print()

    # Migrate incidents
    print("=" * 50)
    print("MIGRATING INCIDENTS")
    print("=" * 50)
    migrate_incidents(cursor, parser, agency_ids, dry_run)
    print()

    if dry_run:
        print("DRY RUN - No changes applied")
    else:
        conn.commit()
        print("All changes committed")

        # Show final counts
        print()
        print("=" * 50)
        print("FINAL COUNTS")
        print("=" * 50)

        cursor.execute('''
            SELECT a.code, COUNT(*)
            FROM messages m
            LEFT JOIN agencies a ON m.agency_id = a.id
            GROUP BY a.code
        ''')
        print("Messages:")
        for code, count in cursor.fetchall():
            print(f"  {code}: {count}")

        cursor.execute('''
            SELECT a.code, COUNT(*)
            FROM incidents i
            LEFT JOIN agencies a ON i.agency_id = a.id
            GROUP BY a.code
        ''')
        print("Incidents:")
        for code, count in cursor.fetchall():
            print(f"  {code}: {count}")

    conn.close()


if __name__ == '__main__':
    import argparse

    argparser = argparse.ArgumentParser(description='Migrate message agency assignments')
    argparser.add_argument('--db', default='data/sagrn.db', help='Path to database')
    argparser.add_argument('--dry-run', action='store_true', help='Show what would change without applying')

    args = argparser.parse_args()

    # Resolve path relative to script location
    if not os.path.isabs(args.db):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, '..', args.db)
    else:
        db_path = args.db

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}")
    print()

    migrate_agencies(db_path, dry_run=args.dry_run)
