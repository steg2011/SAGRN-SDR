import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from app.services.suburb_matcher import get_suburb_matcher


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

    def __init__(self):
        self.suburb_matcher = get_suburb_matcher()

    # SAAS ambulance callsign patterns
    SAAS_CALLSIGN_PATTERN = re.compile(
        r'^([A-Z]{1,4}\d{1,4}|EVENT\d+|MS\d+|LS\d+|SO\d+|HI\d+|OAK\d+)\s+PR:\s*(\d+)\s*-\s*(.+)$'
    )

    # CFS/MFS incident patterns - MFS format with ALARM LEVEL
    CFS_INCIDENT_PATTERN = re.compile(
        r'(CFS|MFS):\s*\*?CFSRES\s+INC[:\s]*([A-Z]?\d+)\s+(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+RESPOND\s+(.+?)(?:,\s*ALARM LEVEL:\s*(\d+))?,\s*(.+?),MAP:([^,]+)'
    )

    # SES/CFS incident pattern - uses P1/P2 priority format instead of ALARM LEVEL
    # Format: MFS: *CFSRES INC:S0030 25/01/26 16:56 RESPOND SEARCH P1 26 DALKEITH DR MOUNT GAMBIER MAP:MGB 2 E12
    SES_CFS_INCIDENT_PATTERN = re.compile(
        r'(CFS|MFS):\s*\*?CFSRES\s+INC:([A-Z]\d+)\s+(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+RESPOND\s+(.+?)\s+P(\d)\s+(.+?)\s+MAP:([^\s,]+)'
    )

    # Simpler CFS message pattern
    CFS_INFO_PATTERN = re.compile(r'^CFS:\s*(.+)$')

    # MFS standalone pattern
    MFS_PATTERN = re.compile(r'^MFS:\s*(.+)$')

    # SES pattern - more comprehensive matching
    SES_PATTERN = re.compile(r'SES[_:\s]|^SES\b')

    # SES incident dispatch pattern (similar to CFS format but for SES)
    SES_INCIDENT_PATTERN = re.compile(
        r'SES:\s*\*?(?:CFSRES|SESRES)\s+INC[:\s]*([A-Z]?\d+)\s+(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2})\s+RESPOND\s+(.+?)(?:,\s*ALARM LEVEL:\s*(\d+))?,\s*(.+?),MAP:([^,]+)'
    )

    # Job ID pattern (D01026, INC0091, S0030)
    JOB_ID_PATTERN = re.compile(r'(D\d{5}|INC\d+|S\d{4})')

    # Unit callsign patterns for agency detection
    # MFS: 3 uppercase letters + exactly 3 digits (e.g., MBR731, APK369)
    MFS_UNIT_PATTERN = re.compile(r'\b[A-Z]{3}\d{3}\b')
    # CFS: 2-4 uppercase letters + exactly 2 digits + optional single letter suffix (e.g., MTB34, KAPD34P)
    CFS_UNIT_PATTERN = re.compile(r'\b[A-Z]{2,4}\d{2}[A-Z]?\b')
    # SES: Units with SES prefix (e.g., SES_RDOS93) - incident number INC:S is primary identifier
    SES_UNIT_PATTERN = re.compile(r'\bSES[_A-Z0-9]+\b')

    # Map reference pattern - includes optional book prefix (e.g., PUG for Port Augusta)
    # Format: [BOOK_PREFIX] PAGE GRID ROW (e.g., "PUG 2 H 15" or "104 N 1")
    MAP_REF_PATTERN = re.compile(r'((?:[A-Z]{2,4}\s+)?\d{1,3}\s+[A-Z]\s+\d{1,2}|MAP:[A-Z]+\s+\d+[A-Z]?\s+[A-Z0-9]+)')

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

    # SAAS incident types - truncated patterns mapped to full names
    # The pager truncates job types, so we map partial strings to complete descriptions
    SAAS_JOB_TYPE_LOOKUP = {
        # Cardiac/Respiratory
        'Cardiac or': 'Cardiac Arrest',
        'Cardiac Ar': 'Cardiac Arrest',
        'CardiacArr': 'Cardiac Arrest',
        'Cardiac': 'Cardiac',
        'Respirator': 'Respiratory Arrest',
        'Respitarre': 'Respiratory Arrest',
        'RespArrest': 'Respiratory Arrest',
        'Breathing': 'Breathing Problems',
        'Breathing ': 'Breathing Problems',

        # General medical
        'Sick Perso': 'Sick Person',
        'Sick Per': 'Sick Person',
        'SickPerson': 'Sick Person',
        'Unconsciou': 'Unconscious',
        'Unconscious': 'Unconscious',
        'Chest Pain': 'Chest Pain',
        'ChestPain': 'Chest Pain',
        'Heart Prob': 'Heart Problem',
        'Heart Problem': 'Heart Problem',
        'HeartProb': 'Heart Problem',
        'Stroke': 'Stroke',
        'Seizure': 'Seizure',
        'Seizures': 'Seizure',
        'Diabetic P': 'Diabetic Problem',
        'Diabetic': 'Diabetic Problem',
        'Allergies': 'Allergic Reaction',
        'Allergic': 'Allergic Reaction',
        'Overdose': 'Overdose',
        'Poisoning': 'Poisoning',

        # Trauma
        'Traumatic': 'Traumatic Injury',
        'Trauma': 'Traumatic Injury',
        'Falls': 'Falls',
        'Fall': 'Falls',
        'Assault': 'Assault',
        'Burns': 'Burns',
        'Burn': 'Burns',
        'Drowning': 'Drowning',
        'Electrocution': 'Electrocution',

        # Hemorrhage
        'Haemorrhag': 'Haemorrhage',
        'Hemorrhage': 'Haemorrhage',
        'Bleeding': 'Bleeding',

        # Pain
        'Back Pain': 'Back Pain',
        'BackPain': 'Back Pain',
        'Abdominal': 'Abdominal Pain',
        'AbdoPain': 'Abdominal Pain',
        'Headache': 'Headache',

        # Mental health
        'Psychiatric': 'Psychiatric',
        'Psych': 'Psychiatric',
        'Mental': 'Mental Health',

        # Obstetric/Pediatric
        'Pregnancy': 'Pregnancy/Childbirth',
        'Childbirth': 'Pregnancy/Childbirth',
        'Labour': 'Labour',
        'Pediatric': 'Pediatric Emergency',

        # Transfer/Admin types
        'TRANSFER': 'Transfer',
        'Transfer': 'Transfer',
        'ADMISSION': 'Admission',
        'Admission': 'Admission',
        'Discharge': 'Discharge',
        'Retrieval': 'Retrieval',

        # Other emergency
        'OTHER EMER': 'Other Emergency',
        'OtherEmerg': 'Other Emergency',
        'Unknown': 'Unknown',
        'MVA': 'Motor Vehicle Accident',
        'Traffic': 'Traffic Accident',
    }

    # List of truncated patterns to search for (in order of specificity)
    SAAS_INCIDENT_PATTERNS = list(SAAS_JOB_TYPE_LOOKUP.keys())

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

        # Check for SES incident dispatch FIRST (before CFS/MFS)
        # SES messages can come through CFSRES system but should be identified as SES
        if content.startswith('SES:') or content.startswith('SES '):
            ses_match = self.SES_INCIDENT_PATTERN.search(content)
            if ses_match:
                parsed.agency = 'SES'
                parsed.incident_number = ses_match.group(1)
                parsed.message_type = 'dispatch'
                parsed.incident_type = ses_match.group(4).strip()
                parsed.alarm_level = int(ses_match.group(5)) if ses_match.group(5) else 1
                parsed.location_text = ses_match.group(6).strip()
                parsed.map_reference = ses_match.group(7).strip()

                # Extract units paged
                units_match = re.search(r':([A-Z0-9_\s]+):$', content)
                if units_match:
                    parsed.units_paged = [u.strip() for u in units_match.group(1).split() if u.strip()]

                return parsed

            # SES info message
            parsed.agency = 'SES'
            if 'STAND DOWN' in content.upper():
                parsed.message_type = 'stand_down'
            else:
                parsed.message_type = 'info'
            return parsed

        # Check for SES/CFS incident dispatch (INC:S format with P1/P2 priority) FIRST
        # This pattern is more specific and should be checked before the general pattern
        ses_cfs_match = self.SES_CFS_INCIDENT_PATTERN.search(content)
        if ses_cfs_match:
            parsed.incident_number = ses_cfs_match.group(2)  # e.g., S0030
            parsed.message_type = 'dispatch'
            parsed.incident_type = ses_cfs_match.group(5).strip()
            parsed.priority = int(ses_cfs_match.group(6))  # P1, P2, etc.
            parsed.alarm_level = int(ses_cfs_match.group(6))  # Use priority as alarm level
            parsed.location_text = ses_cfs_match.group(7).strip()
            parsed.map_reference = ses_cfs_match.group(8).strip()

            # Extract units paged
            units_match = re.search(r':([A-Z0-9_\s]+):$', content)
            if units_match:
                parsed.units_paged = [u.strip() for u in units_match.group(1).split() if u.strip()]

            # Determine agency - INC:S format means SES job
            parsed.agency = self._determine_fire_agency(parsed.incident_number, parsed.units_paged)

            return parsed

        # Check for CFS/MFS incident dispatch (standard format with ALARM LEVEL)
        cfs_match = self.CFS_INCIDENT_PATTERN.search(content)
        if cfs_match:
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

            # Determine agency based on incident number and unit callsigns
            parsed.agency = self._determine_fire_agency(parsed.incident_number, parsed.units_paged)

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
                facility_match = re.match(r':?\s*@([^@]+?)\s+((?:[A-Z]{2,4}\s+)?\d{1,3}\s+[A-Z]\s+\d{1,2})', remainder)
                if facility_match:
                    parsed.location_text = '@' + facility_match.group(1).strip()

            # Extract job ID (D01026 format)
            job_match = re.search(r'(D\d{5})', remainder)
            if job_match:
                parsed.job_id = job_match.group(1)

            # Extract map reference - includes optional book prefix (e.g., "PUG 2 H 15" or "104 N 1")
            # Book prefix is a standalone 2-4 letter code, NOT part of a suburb name
            # Use word boundary to ensure we match complete words only
            map_match = re.search(r'(?:^|\s)(([A-Z]{2,4})\s+(\d{1,2})\s+[A-Z]\s+\d{1,2})(?=\s+D\d{5}|\s+Disp:|\s*$)', remainder)
            if map_match:
                # Check if the potential prefix is a common suburb word/abbreviation - if so, it's not a book prefix
                potential_prefix = map_match.group(2)
                suburb_words = {
                    # Full words
                    'NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL', 'PARK', 'HILLS', 'VALE',
                    'GARDENS', 'BEACH', 'BAY', 'PORT', 'MOUNT', 'POINT', 'VIEW', 'CREEK',
                    'FLAT', 'FLATS', 'DOWNS', 'GROVE', 'HEIGHTS', 'PLAINS', 'RIDGE',
                    # Common abbreviations that might appear at end of suburb names
                    'HTS', 'HGHTS', 'HGTS',  # Heights
                    'VLE', 'VL',  # Vale
                    'VLY', 'VAL',  # Valley
                    'GDNS', 'GDN',  # Gardens
                    'BCH',  # Beach
                    'PK',  # Park
                    'GRV',  # Grove
                    'PLN', 'PLNS',  # Plain/Plains
                }
                if potential_prefix not in suburb_words:
                    parsed.map_reference = map_match.group(1).strip()

            # If no book prefix match, try simple numeric pattern
            if not parsed.map_reference:
                map_match = re.search(r'(\d{1,3}\s+[A-Z]\s+\d{1,2})(?=\s+D\d{5}|\s+Disp:|\s*$)', remainder)
                if map_match:
                    parsed.map_reference = map_match.group(1)

            # Extract dispatch time
            disp_match = self.DISPATCH_TIME_PATTERN.search(remainder)
            if disp_match:
                parsed.dispatch_time = disp_match.group(1)

            # Extract incident type using lookup table
            # Search for truncated patterns and map to full names
            parsed.incident_type = self._extract_saas_incident_type(remainder)

            # Extract suburb using the suburb lookup table
            # SAAS format varies:
            #   - Simple: "SUBURB MAP_REF JOB_ID Disp: TIME INCIDENT_TYPE"
            #   - With codes: ": H715 SUBURB MAP_REF JOB_ID Disp: TIME"
            #   - With facility: ": @FACILITY_NAME SUBURB MAP_REF JOB_ID"
            # Use the suburb matcher to scan for known suburb names

            # Determine the text to search for suburb
            if parsed.map_reference:
                # Search in text before the map reference
                search_text = remainder.split(parsed.map_reference)[0].strip()
            else:
                # Search in text before the job ID or dispatch time
                search_text = remainder
                if parsed.job_id:
                    search_text = remainder.split(parsed.job_id)[0].strip()
                elif 'Disp:' in remainder:
                    search_text = remainder.split('Disp:')[0].strip()

            # Clean up the search text
            # Remove leading colon and whitespace (common in messages with codes)
            search_text = search_text.lstrip(': ')
            # Replace underscores with spaces
            search_text = search_text.replace('_', ' ')

            # For facility messages, try to extract suburb from after facility name
            if '@' in search_text:
                # Find the facility name (between @ and the next known suburb or map ref)
                facility_start = search_text.find('@')
                facility_text = search_text[facility_start:]
                # Suburb is usually at the end of facility text, search for it
                parsed.suburb = self.suburb_matcher.extract_suburb_from_text(facility_text)
            else:
                # Non-facility message - scan for known suburb names
                parsed.suburb = self.suburb_matcher.extract_suburb_from_text(search_text)

            return parsed

        # Check for SES (catch any remaining SES patterns not caught above)
        if self.SES_PATTERN.search(content):
            parsed.agency = 'SES'
            if 'STAND DOWN' in content.upper():
                parsed.message_type = 'stand_down'
            else:
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

            # Try to parse as a fire service dispatch notification
            # Remove 'NOTIFICATION ' prefix and parse the rest
            notification_content = content[len('NOTIFICATION '):].strip()

            # Try SES/CFS format first (INC:S with P1/P2)
            notif_ses_match = self.SES_CFS_INCIDENT_PATTERN.search(notification_content)
            if notif_ses_match:
                parsed.incident_number = notif_ses_match.group(2)
                parsed.incident_type = notif_ses_match.group(5).strip()
                parsed.priority = int(notif_ses_match.group(6))
                parsed.alarm_level = int(notif_ses_match.group(6))
                parsed.location_text = notif_ses_match.group(7).strip()
                parsed.map_reference = notif_ses_match.group(8).strip()

                # Extract units paged
                units_match = re.search(r':([A-Z0-9_\s]+):$', notification_content)
                if units_match:
                    parsed.units_paged = [u.strip() for u in units_match.group(1).split() if u.strip()]

                # Determine agency based on incident number and units
                parsed.agency = self._determine_fire_agency(parsed.incident_number, parsed.units_paged)
                return parsed

            # Try standard MFS format (with ALARM LEVEL)
            notif_match = self.CFS_INCIDENT_PATTERN.search(notification_content)
            if notif_match:
                parsed.incident_number = notif_match.group(2)
                parsed.incident_type = notif_match.group(5).strip()
                parsed.alarm_level = int(notif_match.group(6)) if notif_match.group(6) else 1
                parsed.location_text = notif_match.group(7).strip()
                parsed.map_reference = notif_match.group(8).strip()

                # Extract units paged
                units_match = re.search(r':([A-Z0-9_\s]+):$', notification_content)
                if units_match:
                    parsed.units_paged = [u.strip() for u in units_match.group(1).split() if u.strip()]

                # Determine agency based on incident number and units
                parsed.agency = self._determine_fire_agency(parsed.incident_number, parsed.units_paged)
                return parsed

            # Fallback: try to extract agency from content keywords
            if 'SES' in content:
                parsed.agency = 'SES'
            elif 'CFS' in content:
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

    def _extract_saas_incident_type(self, text: str) -> Optional[str]:
        """
        Extract SAAS incident type from message text using lookup table.
        Handles truncated job types by matching patterns and returning full names.
        """
        # Sort patterns by length (longest first) for more specific matches
        sorted_patterns = sorted(self.SAAS_INCIDENT_PATTERNS, key=len, reverse=True)

        for pattern in sorted_patterns:
            if pattern in text:
                return self.SAAS_JOB_TYPE_LOOKUP[pattern]

        # Fuzzy matching fallback - check for partial matches using word boundaries
        # This prevents matching substrings inside other words (e.g., 'od' in 'NORWOOD')
        text_lower = text.lower()

        # Check for common patterns that might be split or slightly different
        # Use word boundary matching to avoid false positives
        fuzzy_matches = [
            ('cardiac', 'Cardiac'),
            ('arrest', 'Cardiac Arrest'),
            ('breathing', 'Breathing Problems'),
            ('unconscious', 'Unconscious'),
            ('chest', 'Chest Pain'),
            ('heart', 'Heart Problem'),
            ('trauma', 'Traumatic Injury'),
            ('fall', 'Falls'),
            ('seizure', 'Seizure'),
            ('stroke', 'Stroke'),
            ('diabetic', 'Diabetic Problem'),
            ('overdose', 'Overdose'),
            ('bleed', 'Bleeding'),
            ('haemorrhag', 'Haemorrhage'),
            ('hemorrhag', 'Haemorrhage'),
            ('assault', 'Assault'),
            ('burn', 'Burns'),
            ('drown', 'Drowning'),
            ('psychiatric', 'Psychiatric'),
            ('transfer', 'Transfer'),
            ('admission', 'Admission'),
            ('discharge', 'Discharge'),
            ('retrieval', 'Retrieval'),
            ('abdomin', 'Abdominal Pain'),
            ('headache', 'Headache'),
            ('back pain', 'Back Pain'),
            ('allergic', 'Allergic Reaction'),
            ('sick', 'Sick Person'),
        ]

        for keyword, full_name in fuzzy_matches:
            # Use word boundary regex to avoid matching substrings inside other words
            if re.search(r'\b' + re.escape(keyword), text_lower):
                return full_name

        return None

    def _determine_fire_agency(self, incident_number: str, units_paged: list) -> str:
        """
        Determine the fire agency (MFS, CFS, or SES) based on incident number and unit callsigns.

        Rules:
        - SES: Incident number starts with 'S' (from INC:S format, e.g., S0030)
        - MFS: Unit callsigns match pattern [A-Z]{3}\d{3} (e.g., MBR731, APK369)
        - CFS: Unit callsigns match pattern [A-Z]{2,4}\d{2}[A-Z]? (e.g., MTB34, KAPD34P)
        """
        # Check for SES incident number (starts with 'S')
        if incident_number and incident_number.startswith('S'):
            return 'SES'

        # Count MFS and CFS units to determine agency
        mfs_count = 0
        cfs_count = 0

        for unit in units_paged:
            # Skip duty officer callsigns and other non-appliance callsigns
            if '_' in unit or unit.startswith('RDOS') or unit.startswith('SDO'):
                continue

            # Check for MFS pattern: 3 letters + 3 digits (e.g., MBR731)
            if self.MFS_UNIT_PATTERN.fullmatch(unit):
                mfs_count += 1
            # Check for CFS pattern: 2-4 letters + 2 digits + optional letter (e.g., MTB34, KAPD34P)
            elif self.CFS_UNIT_PATTERN.fullmatch(unit):
                cfs_count += 1

        # Determine agency based on unit counts
        if mfs_count > 0 and cfs_count == 0:
            return 'MFS'
        elif cfs_count > 0 and mfs_count == 0:
            return 'CFS'
        elif mfs_count > 0 and cfs_count > 0:
            # Mixed response - use majority, default to MFS if equal
            return 'MFS' if mfs_count >= cfs_count else 'CFS'
        else:
            # No recognizable units - default to MFS (as dispatched through MFS system)
            return 'MFS'

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
