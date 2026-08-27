"""
Integration with CFS/MFS incident feeds for authoritative location data and job status.

Uses two feeds:
- JSON feed: cfs_current_incidents.json — all current incidents with lat/long, status, resources
- CAP feed: cfs_cap_incidents.xml — detailed descriptions, severity, polygons (subset of incidents)

The JSON feed is the primary source for coordinates. When a CFS/MFS incident matches
a pager-created incident, the official coordinates overwrite the local geocoding estimate.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import httpx
from rapidfuzz import fuzz
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.models import Incident, Agency

settings = get_settings()


class CFSIntegrationService:
    """Integration with CFS/MFS incident tracker for official location and status data."""

    async def fetch_current_incidents_json(self) -> List[Dict]:
        """Fetch current incidents from the JSON feed (primary source)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(settings.cfs_incidents_json)

                if response.status_code != 200:
                    print(f"Failed to fetch CFS JSON feed: {response.status_code}")
                    return []

                return self._parse_incidents_json(response.json())

        except Exception as e:
            print(f"Error fetching CFS JSON feed: {e}")
            return []

    def _parse_incidents_json(self, data) -> List[Dict]:
        """Parse the CFS JSON feed into normalized incident dicts."""
        incidents = []

        # Handle both array and object-wrapped formats
        items = data if isinstance(data, list) else data.get('incidents', [])

        for item in items:
            inc_data = {
                'incident_number': str(item.get('IncidentNo', '')),
                'date': item.get('Date', ''),
                'time': item.get('Time', ''),
                'location_name': item.get('Location_name', ''),
                'region': item.get('Region', ''),
                'type': item.get('Type', ''),
                'status': item.get('Status', ''),
                'level': item.get('Level', 1),
                'resources': item.get('Resources', 0),
                'aircraft': item.get('Aircraft', 0),
            }

            # Parse coordinates from "lat,lon" string
            location_str = item.get('Location', '')
            if location_str and ',' in str(location_str):
                try:
                    parts = str(location_str).split(',')
                    inc_data['latitude'] = float(parts[0])
                    inc_data['longitude'] = float(parts[1])
                except (ValueError, IndexError):
                    pass

            # Parse Location_name into suburb and address
            # Format is typically "SUBURB, STREET_ADDRESS" or just "SUBURB"
            loc_name = inc_data['location_name']
            if ',' in loc_name:
                parts = loc_name.split(',', 1)
                inc_data['suburb'] = parts[0].strip()
                inc_data['address'] = parts[1].strip()
            else:
                inc_data['suburb'] = loc_name.strip()
                inc_data['address'] = ''

            if inc_data['incident_number']:
                incidents.append(inc_data)

        return incidents

    async def fetch_cap_incidents(self) -> List[Dict]:
        """Fetch CAP format incidents from XML feed for enrichment data."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(settings.cfs_cap_xml)

                if response.status_code != 200:
                    print(f"Failed to fetch CFS CAP incidents: {response.status_code}")
                    return []

                return self._parse_cap_xml(response.text)

        except Exception as e:
            print(f"Error fetching CFS CAP incidents: {e}")
            return []

    def _parse_cap_xml(self, xml_content: str) -> List[Dict]:
        """Parse CAP format incidents XML."""
        incidents = []

        try:
            namespaces = {
                'cap': 'urn:oasis:names:tc:emergency:cap:1.2',
                'atom': 'http://www.w3.org/2005/Atom'
            }

            root = ET.fromstring(xml_content)

            # Find alerts within Atom entries
            for entry in root.findall('.//atom:entry', namespaces):
                content = entry.find('atom:content', namespaces)
                if content is None:
                    continue

                alert = content.find('cap:alert', namespaces)
                if alert is None:
                    # Try direct alert without content wrapper
                    alert = entry.find('.//cap:alert', namespaces)
                if alert is None:
                    continue

                info = alert.find('cap:info', namespaces)
                if info is None:
                    continue

                inc_data = {
                    'identifier': self._get_text(alert, 'cap:identifier', namespaces),
                    'status': self._get_text(alert, 'cap:status', namespaces),
                    'headline': self._get_text(info, 'cap:headline', namespaces),
                    'description': self._get_text(info, 'cap:description', namespaces),
                    'urgency': self._get_text(info, 'cap:urgency', namespaces),
                    'severity': self._get_text(info, 'cap:severity', namespaces),
                    'certainty': self._get_text(info, 'cap:certainty', namespaces),
                    'event': self._get_text(info, 'cap:event', namespaces),
                }

                # Extract incident number from the incidents element
                incidents_text = self._get_text(alert, 'cap:incidents', namespaces)
                if incidents_text:
                    # Format: "Location: IncidentNumber"
                    if ':' in incidents_text:
                        inc_data['incident_ref'] = incidents_text.split(':')[-1].strip()
                    else:
                        inc_data['incident_ref'] = incidents_text.strip()

                # Extract parameters (IncidentName, Status, etc.)
                for param in info.findall('cap:parameter', namespaces):
                    name = self._get_text(param, 'cap:valueName', namespaces)
                    value = self._get_text(param, 'cap:value', namespaces)
                    if name and value:
                        inc_data[f'param_{name}'] = value

                # Get area info
                area = info.find('cap:area', namespaces)
                if area:
                    inc_data['area_desc'] = self._get_text(area, 'cap:areaDesc', namespaces)

                    circle = self._get_text(area, 'cap:circle', namespaces)
                    if circle:
                        parts = circle.split()
                        if parts:
                            coords = parts[0].split(',')
                            if len(coords) == 2:
                                try:
                                    inc_data['latitude'] = float(coords[0])
                                    inc_data['longitude'] = float(coords[1])
                                except ValueError:
                                    pass

                incidents.append(inc_data)

            # Also try finding alerts directly (not wrapped in Atom)
            for alert in root.findall('.//cap:alert', namespaces):
                info = alert.find('cap:info', namespaces)
                if info is None:
                    continue

                inc_data = {
                    'identifier': self._get_text(alert, 'cap:identifier', namespaces),
                    'headline': self._get_text(info, 'cap:headline', namespaces),
                    'description': self._get_text(info, 'cap:description', namespaces),
                    'severity': self._get_text(info, 'cap:severity', namespaces),
                    'event': self._get_text(info, 'cap:event', namespaces),
                }

                area = info.find('cap:area', namespaces)
                if area:
                    inc_data['area_desc'] = self._get_text(area, 'cap:areaDesc', namespaces)
                    circle = self._get_text(area, 'cap:circle', namespaces)
                    if circle:
                        parts = circle.split()
                        if parts:
                            coords = parts[0].split(',')
                            if len(coords) == 2:
                                try:
                                    inc_data['latitude'] = float(coords[0])
                                    inc_data['longitude'] = float(coords[1])
                                except ValueError:
                                    pass

                if inc_data.get('identifier'):
                    incidents.append(inc_data)

        except ET.ParseError as e:
            print(f"CAP XML parse error: {e}")

        return incidents

    def _get_text(self, element, path: str, namespaces: dict = None) -> Optional[str]:
        """Safely get text from XML element."""
        if namespaces:
            child = element.find(path, namespaces)
        else:
            child = element.find(path)
        return child.text if child is not None else None

    async def update_incidents(self, db: AsyncSession):
        """Update local incidents with CFS/MFS JSON feed data and manage status lifecycle.

        Status priority (highest to lowest):
        1. CAP feed status — gold standard (not all incidents have CAP)
        2. JSON feed status — gold standard (current incidents only)
        3. Pager message — initial source, considered stale after 1 hour without feed confirmation
        """
        cfs_incidents = await self.fetch_current_incidents_json()

        # Get agency objects
        result = await db.execute(select(Agency))
        agencies = {a.code: a for a in result.scalars().all()}

        cfs_agency = agencies.get('CFS')
        mfs_agency = agencies.get('MFS')
        ses_agency = agencies.get('SES')

        if not cfs_agency:
            return

        agency_ids = [a.id for a in [cfs_agency, mfs_agency, ses_agency] if a]

        # Get recent local incidents (active ones for matching, all for status management)
        cutoff = datetime.utcnow() - timedelta(hours=48)
        result = await db.execute(
            select(Incident)
            .options(selectinload(Incident.agency))
            .where(
                and_(
                    Incident.incident_date >= cutoff,
                    Incident.agency_id.in_(agency_ids)
                )
            )
        )
        local_incidents = result.scalars().all()

        # Track which local incidents got matched to a feed entry
        matched_ids = set()

        if cfs_incidents:
            for cfs_inc in cfs_incidents:
                inc_num = cfs_inc.get('incident_number', '')
                if not inc_num:
                    continue

                # Determine which agency this belongs to
                region = cfs_inc.get('region', '')
                if str(region).upper() == 'MFS':
                    target_agency = mfs_agency
                else:
                    target_agency = cfs_agency

                if not target_agency:
                    continue

                # Try exact match by incident number
                matched_incident = None
                for local_inc in local_incidents:
                    if local_inc.incident_number == inc_num:
                        matched_incident = local_inc
                        break

                # Try fuzzy match by location + time
                if not matched_incident:
                    matched_incident = self._fuzzy_match_incident(
                        cfs_inc, local_incidents, target_agency
                    )

                if matched_incident:
                    self._apply_cfs_data(matched_incident, cfs_inc)
                    matched_ids.add(matched_incident.id)

        # Also fetch CAP data for enrichment
        cap_incidents = await self.fetch_cap_incidents()
        if cap_incidents:
            self._enrich_with_cap(local_incidents, cap_incidents)

        # --- Status lifecycle management ---
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        for inc in local_incidents:
            if inc.status == 'closed':
                continue

            # If this incident was matched to a current feed entry, it stays active
            if inc.id in matched_ids:
                continue

            # If it previously had a CFS feed update (cfs_last_update set),
            # but is no longer in the current feed → it's closed
            if inc.cfs_last_update and cfs_incidents:
                inc.status = 'closed'
                if not inc.closed_at:
                    inc.closed_at = now
                continue

            # Pager-only incidents (never matched to feed): close after 1 hour
            if not inc.cfs_last_update and inc.created_at < one_hour_ago:
                inc.status = 'closed'
                if not inc.closed_at:
                    inc.closed_at = now

        await db.commit()

    def _fuzzy_match_incident(
        self, cfs_inc: Dict, local_incidents: List[Incident],
        target_agency: Agency
    ) -> Optional[Incident]:
        """Fuzzy match a CFS feed incident to a local pager incident."""
        cfs_suburb = cfs_inc.get('suburb', '').upper()
        cfs_address = cfs_inc.get('address', '').upper()
        cfs_type = cfs_inc.get('type', '').upper()
        cfs_location = f"{cfs_address} {cfs_suburb}".strip()

        if not cfs_location:
            return None

        best_match = None
        best_score = 0

        for local_inc in local_incidents:
            if local_inc.agency_id != target_agency.id:
                continue

            # Already has official data
            if local_inc.location_source == 'OFFICIAL_FEED':
                continue

            # Build local location string
            local_location = f"{local_inc.address or ''} {local_inc.suburb or ''}".strip().upper()
            if not local_location:
                continue

            # Fuzzy compare locations
            location_score = fuzz.token_sort_ratio(cfs_location, local_location)

            # Boost score if incident types match
            type_bonus = 0
            if cfs_type and local_inc.incident_type:
                type_score = fuzz.token_sort_ratio(cfs_type, local_inc.incident_type.upper())
                if type_score > 70:
                    type_bonus = 10

            # Boost if suburbs match exactly
            suburb_bonus = 0
            if cfs_suburb and local_inc.suburb and cfs_suburb == local_inc.suburb.upper():
                suburb_bonus = 15

            total_score = location_score + type_bonus + suburb_bonus

            if total_score > best_score and location_score >= 60:
                best_score = total_score
                best_match = local_inc

        # Require a reasonable match quality
        if best_score >= 75:
            return best_match

        return None

    def _apply_cfs_data(self, incident: Incident, cfs_inc: Dict):
        """Apply CFS feed data to a local incident."""
        # Update coordinates (authoritative)
        if cfs_inc.get('latitude') and cfs_inc.get('longitude'):
            incident.latitude = cfs_inc['latitude']
            incident.longitude = cfs_inc['longitude']
            incident.geocode_success = True
            incident.geocode_attempted = True
            incident.location_source = 'OFFICIAL_FEED'
            incident.location_confidence = 100.0

        # Update status
        status = cfs_inc.get('status', '')
        if status:
            incident.cfs_status = status
            if status.upper() in ('COMPLETE', 'SAFE'):
                incident.status = 'closed'
                if not incident.closed_at:
                    incident.closed_at = datetime.utcnow()

        # Update address from CFS if we don't have one
        if cfs_inc.get('address') and not incident.address:
            incident.address = cfs_inc['address']
        if cfs_inc.get('suburb') and not incident.suburb:
            incident.suburb = cfs_inc['suburb']

        # Update resources count
        resources = cfs_inc.get('resources', 0)
        if resources:
            incident.cfs_resources = resources

        incident.cfs_last_update = datetime.utcnow()

    def _enrich_with_cap(self, local_incidents: List[Incident], cap_incidents: List[Dict]):
        """Enrich local incidents with CAP feed data (descriptions, severity)."""
        for cap_inc in cap_incidents:
            description = cap_inc.get('description', '')
            if not description:
                continue

            # Try to match by incident reference
            inc_ref = cap_inc.get('incident_ref', '')
            area_desc = cap_inc.get('area_desc', '')

            for local_inc in local_incidents:
                matched = False

                # Match by incident number in reference
                if inc_ref and local_inc.incident_number in inc_ref:
                    matched = True

                # Match by area description vs suburb
                if not matched and area_desc and local_inc.suburb:
                    if local_inc.suburb.upper() in area_desc.upper():
                        # Also check type matches
                        event = cap_inc.get('event', '')
                        if event and local_inc.incident_type:
                            if fuzz.token_sort_ratio(event, local_inc.incident_type) > 70:
                                matched = True

                if matched:
                    local_inc.cfs_description = description

                    # Update coordinates from CAP if we don't have them yet
                    if not local_inc.latitude and cap_inc.get('latitude'):
                        local_inc.latitude = cap_inc['latitude']
                        local_inc.longitude = cap_inc.get('longitude')
                        local_inc.geocode_success = True
                        local_inc.geocode_attempted = True
                        local_inc.location_source = 'OFFICIAL_FEED'
                        local_inc.location_confidence = 100.0

    async def get_incident_status(self, incident_number: str) -> Optional[Dict]:
        """Get status for a specific incident from CFS feed."""
        incidents = await self.fetch_current_incidents_json()
        for inc in incidents:
            if inc.get('incident_number') == incident_number:
                return inc
        return None
