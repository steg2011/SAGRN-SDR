import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass
class ParsedMessage:
    """Parsed pager message structure"""
    raw_message: str
    timestamp: datetime
    agency: Optional[str] = None
    message_type: Optional[str] = None  # dispatch, update, stand_down, info
    callsign: Optional[str] = None
    priority: Optional[int] = None
    location_text: Optional[str] = None
    suburb: Optional[str] = None
    map_reference: Optional[str] = None
    job_id: Optional[str] = None
    dispatch_time: Optional[str] = None
    incident_type: Optional[str] = None
    incident_number: Optional[str] = None
    alarm_level: Optional[int] = None
    flex_speed: Optional[str] = None
    flex_frame: Optional[str] = None
    capcode: Optional[str] = None
    is_saas_job: bool = False
    units_paged: list = None

    def __post_init__(self):
        if self.units_paged is None:
            self.units_paged = []


class MessageParser:
    """Parser for SAGRN pager messages"""

    # SAAS ambulance callsign patterns
    SAAS_CALLSIGN_PATTERN = re.compile(
        r'^([A-Z]{1,4}\d{1,4}|EVENT\d+|MS\d+|LS\d+|SO\d+|HI\d+|OAK\d+)\s+PR:\s*(\d+)\s*-\s*(.+)$'
    )

    # CFS/MFS incident patterns
    CFS_INCIDENT_PATTERN = re.compile(
        r'(CFS|MFS):\s*\*?CFSRES\s+INC[:\s]*([A-Z]?\d+)\s+(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+RESPOND\s+(.+?)(?:,\s*ALARM LEVEL:\s*(\d+))?,\s*(.+?),MAP:([^,]+)'
    )

    # Simpler CFS message pattern
    CFS_INFO_PATTERN = re.compile(r'^CFS:\s*(.+)$')

    # MFS standalone pattern
    MFS_PATTERN = re.compile(r'^MFS:\s*(.+)$')

    # SES pattern
    SES_PATTERN = re.compile(r'SES[_:]')

    # Job ID pattern (D01026, INC0091, S0030)
    JOB_ID_PATTERN = re.compile(r'(D\d{5}|INC\d+|S\d{4})')

    # Map reference pattern
    MAP_REF_PATTERN = re.compile(r'(\d{1,3}\s+[A-Z]\s+\d{1,2}|MAP:[A-Z]+\s+\d+[A-Z]?\s+[A-Z0-9]+)')

    # Dispatch time pattern
    DISPATCH_TIME_PATTERN = re.compile(r'Disp:\s*(\d{2}:\d{2})')

    # FLEX line pattern
    FLEX_LINE_PATTERN = re.compile(
        r'FLEX\|(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\|(\d+/\d+/[A-Z]/[A-Z])\|([^|]+)\|(\d+)\|ALN\|(.+)$'
    )

    # Alternative FLEX pattern
    FLEX_ALT_PATTERN = re.compile(
        r'FLEX:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\d+/\d+/[A-Z])\s+([^\[]+)\[(\d+)\]'
    )

    # Simple timestamp pattern for older format
    SIMPLE_TIMESTAMP_PATTERN = re.compile(
        r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*ALN\|(.+)$'
    )

    # SAAS incident types
    SAAS_INCIDENT_TYPES = [
        'Sick Perso', 'Cardiac or', 'Falls', 'Breathing', 'Unconsciou',
        'Traumatic', 'Chest Pain', 'OTHER EMER', 'TRANSFER', 'Haemorrhag',
        'Back Pain', 'Diabetic P', 'Drowning', 'ADMISSION', 'Discharge',
        'Retrieval', 'Allergies', 'Stroke', 'Seizure', 'Psychiatric',
        'Abdominal', 'Headache', 'Overdose', 'Assault', 'Burns'
    ]

    # CFS/MFS incident types
    FIRE_INCIDENT_TYPES = [
        'STRUCTURE FIRE', 'BUSHFIRE', 'GRASS FIRE', 'FIRE ALARM',
        'TREE DOWN', 'ASSIST ESO AGENCY', 'SEARCH', 'HAZMAT',
        'MOTOR VEHICLE ACCIDENT', 'MVA', 'RESCUE'
    ]

    # Watchdog pattern (to ignore)
    WATCHDOG_PATTERN = re.compile(r'mhs-watchdog\s+\d+')

    def parse(self, line: str) -> Optional[ParsedMessage]:
        """Parse a single pager log line"""
        line = line.strip()
        if not line:
            return None

        # Skip watchdog messages
        if self.WATCHDOG_PATTERN.search(line):
            return None

        # Try to extract timestamp and message content
        timestamp = None
        content = line
        flex_speed = None
        flex_frame = None
        capcode = None

        # Try FLEX format first
        flex_match = self.FLEX_LINE_PATTERN.match(line)
        if flex_match:
            timestamp = self._parse_timestamp(flex_match.group(1))
            flex_speed = flex_match.group(2)
            flex_frame = flex_match.group(3)
            capcode = flex_match.group(4)
            content = flex_match.group(5)
        else:
            # Try alternative FLEX format
            flex_alt_match = self.FLEX_ALT_PATTERN.match(line)
            if flex_alt_match:
                timestamp = self._parse_timestamp(flex_alt_match.group(1))
                flex_speed = flex_alt_match.group(2)
                capcode = flex_alt_match.group(4)
                content = line.split(']')[-1].strip() if ']' in line else line
            else:
                # Try simple timestamp format
                simple_match = self.SIMPLE_TIMESTAMP_PATTERN.match(line)
                if simple_match:
                    timestamp = self._parse_timestamp(simple_match.group(1))
                    content = simple_match.group(2)

        if timestamp is None:
            timestamp = datetime.utcnow()

        # Skip partial/continuation messages
        if content.startswith(' ') and len(content) < 50:
            return None

        # Create base parsed message
        parsed = ParsedMessage(
            raw_message=line,
            timestamp=timestamp,
            flex_speed=flex_speed,
            flex_frame=flex_frame,
            capcode=capcode
        )

        # Try to identify agency and parse accordingly
        parsed = self._identify_agency_and_parse(content, parsed)

        return parsed

    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime"""
        try:
            return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None

    def _identify_agency_and_parse(self, content: str, parsed: ParsedMessage) -> ParsedMessage:
        """Identify agency and parse message content"""

        # Check for CFS/MFS incident dispatch
        cfs_match = self.CFS_INCIDENT_PATTERN.search(content)
        if cfs_match:
            parsed.agency = cfs_match.group(1)  # CFS or MFS
            parsed.incident_number = cfs_match.group(2)
            parsed.message_type = 'dispatch'
            parsed.incident_type = cfs_match.group(5).strip()
            parsed.alarm_level = int(cfs_match.group(6)) if cfs_match.group(6) else 1
            parsed.location_text = cfs_match.group(7).strip()
            parsed.map_reference = cfs_match.group(8).strip()

            # Extract units paged
            units_match = re.search(r':([A-Z0-9_\s]+):$', content)
            if units_match:
                parsed.units_paged = [u.strip() for u in units_match.group(1).split() if u.strip()]

            return parsed

        # Check for CFS info messages
        if content.startswith('CFS:'):
            parsed.agency = 'CFS'
            parsed.message_type = 'info'

            if 'STAND DOWN' in content.upper():
                parsed.message_type = 'stand_down'
            elif 'SIG INC' in content:
                parsed.message_type = 'significant_incident'
            elif 'AIR OPS' in content:
                parsed.message_type = 'air_ops'

            return parsed

        # Check for MFS messages (non-CFSRES)
        if content.startswith('MFS:'):
            parsed.agency = 'MFS'

            if 'STAND DOWN' in content.upper():
                parsed.message_type = 'stand_down'
            elif 'STOP FOR' in content:
                parsed.message_type = 'stop'
            else:
                parsed.message_type = 'info'

            return parsed

        # Check for SAAS ambulance dispatch
        saas_match = self.SAAS_CALLSIGN_PATTERN.match(content)
        if saas_match:
            parsed.agency = 'SAAS'
            parsed.callsign = saas_match.group(1)
            parsed.priority = int(saas_match.group(2))
            parsed.message_type = 'dispatch'
            parsed.is_saas_job = True

            remainder = saas_match.group(3)

            # Extract location (usually suburb name)
            # Format: "SUBURB MAP_REF JOB_ID Disp: TIME INCIDENT_TYPE"
            # Or: "@FACILITY_NAME SUBURB MAP_REF JOB_ID Disp: TIME INCIDENT_TYPE"

            # Check for facility prefix
            if remainder.startswith('@') or ': @' in remainder:
                facility_match = re.match(r':?\s*@([^@]+?)\s+(\d{1,3}\s+[A-Z]\s+\d{1,2})', remainder)
                if facility_match:
                    parsed.location_text = '@' + facility_match.group(1).strip()

            # Extract job ID (D01026 format)
            job_match = re.search(r'(D\d{5})', remainder)
            if job_match:
                parsed.job_id = job_match.group(1)

            # Extract map reference
            map_match = re.search(r'(\d{1,3}\s+[A-Z]\s+\d{1,2})', remainder)
            if map_match:
                parsed.map_reference = map_match.group(1)

            # Extract dispatch time
            disp_match = self.DISPATCH_TIME_PATTERN.search(remainder)
            if disp_match:
                parsed.dispatch_time = disp_match.group(1)

            # Extract incident type (last word/phrase)
            for inc_type in self.SAAS_INCIDENT_TYPES:
                if inc_type in remainder:
                    parsed.incident_type = inc_type
                    break

            # Extract suburb - usually after map ref, or first capitalized word
            # Try to get suburb from before map reference
            if parsed.map_reference:
                parts = remainder.split(parsed.map_reference)[0].strip().split()
                # Look for suburb (capitalized word before map ref)
                for part in reversed(parts):
                    if part.isupper() and len(part) > 2 and not part.startswith('@'):
                        parsed.suburb = part
                        break

            return parsed

        # Check for SES
        if self.SES_PATTERN.search(content):
            parsed.agency = 'SES'
            parsed.message_type = 'info'
            return parsed

        # Check for MedStar
        if 'MEDSTAR' in content.upper() or content.startswith('MS') and 'PR:' in content:
            parsed.agency = 'MedStar'
            parsed.message_type = 'dispatch'
            return parsed

        # Check for notification/personal messages
        if content.startswith('NOTIFICATION'):
            parsed.message_type = 'notification'
            # Try to extract agency from content
            if 'CFS' in content:
                parsed.agency = 'CFS'
            elif 'MFS' in content:
                parsed.agency = 'MFS'
            return parsed

        # Check for "DISREGARD" or similar
        if 'DISREGARD' in content.upper():
            parsed.message_type = 'disregard'
            return parsed

        # Generic/unknown message
        parsed.agency = 'UNKNOWN'
        parsed.message_type = 'other'

        return parsed

    def is_saas_job(self, parsed: ParsedMessage) -> bool:
        """Check if this is a SAAS job (should not be geocoded as they don't have addresses)"""
        if parsed.agency != 'SAAS':
            return False

        # SAAS transfers and facility jobs don't have street addresses
        if parsed.incident_type in ['TRANSFER', 'ADMISSION', 'Discharge', 'Retrieval']:
            return True

        # Jobs at facilities (starting with @) don't need geocoding
        if parsed.location_text and parsed.location_text.startswith('@'):
            return True

        return False
