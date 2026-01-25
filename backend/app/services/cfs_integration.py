import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional, List, Dict
import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import Incident, Agency

settings = get_settings()


class CFSIntegrationService:
    """
    Integration with CFS incident tracker for final location info and job status.
    Uses the public XML feeds from data.eso.sa.gov.au
    """

    async def fetch_current_incidents(self) -> List[Dict]:
        """Fetch current CFS incidents from XML feed"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(settings.cfs_incidents_xml)

                if response.status_code != 200:
                    print(f"Failed to fetch CFS incidents: {response.status_code}")
                    return []

                return self._parse_incidents_xml(response.text)

        except Exception as e:
            print(f"Error fetching CFS incidents: {e}")
            return []

    async def fetch_cap_incidents(self) -> List[Dict]:
        """Fetch CAP format incidents from XML feed"""
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

    def _parse_incidents_xml(self, xml_content: str) -> List[Dict]:
        """Parse CFS current incidents XML"""
        incidents = []

        try:
            root = ET.fromstring(xml_content)

            for incident in root.findall('.//incident'):
                inc_data = {
                    'incident_number': self._get_text(incident, 'incident_number'),
                    'status': self._get_text(incident, 'status'),
                    'type': self._get_text(incident, 'type'),
                    'location': self._get_text(incident, 'location'),
                    'suburb': self._get_text(incident, 'suburb'),
                    'region': self._get_text(incident, 'region'),
                    'latitude': self._get_float(incident, 'latitude'),
                    'longitude': self._get_float(incident, 'longitude'),
                    'last_updated': self._get_text(incident, 'last_updated'),
                    'warning_level': self._get_text(incident, 'warning_level'),
                }

                if inc_data['incident_number']:
                    incidents.append(inc_data)

        except ET.ParseError as e:
            print(f"XML parse error: {e}")

        return incidents

    def _parse_cap_xml(self, xml_content: str) -> List[Dict]:
        """Parse CAP format incidents XML"""
        incidents = []

        try:
            # CAP format uses namespaces
            namespaces = {
                'cap': 'urn:oasis:names:tc:emergency:cap:1.2',
                'atom': 'http://www.w3.org/2005/Atom'
            }

            root = ET.fromstring(xml_content)

            # Try to find alerts in CAP format
            for alert in root.findall('.//cap:alert', namespaces):
                info = alert.find('cap:info', namespaces)
                if info is None:
                    continue

                inc_data = {
                    'identifier': self._get_text(alert, 'cap:identifier', namespaces),
                    'status': self._get_text(alert, 'cap:status', namespaces),
                    'msgType': self._get_text(alert, 'cap:msgType', namespaces),
                    'headline': self._get_text(info, 'cap:headline', namespaces),
                    'description': self._get_text(info, 'cap:description', namespaces),
                    'urgency': self._get_text(info, 'cap:urgency', namespaces),
                    'severity': self._get_text(info, 'cap:severity', namespaces),
                    'certainty': self._get_text(info, 'cap:certainty', namespaces),
                }

                # Get area info
                area = info.find('cap:area', namespaces)
                if area:
                    inc_data['area_desc'] = self._get_text(area, 'cap:areaDesc', namespaces)

                    # Get polygon or circle for location
                    polygon = self._get_text(area, 'cap:polygon', namespaces)
                    circle = self._get_text(area, 'cap:circle', namespaces)

                    if circle:
                        # Format: lat,lon radius
                        parts = circle.split()
                        if parts:
                            coords = parts[0].split(',')
                            if len(coords) == 2:
                                inc_data['latitude'] = float(coords[0])
                                inc_data['longitude'] = float(coords[1])

                incidents.append(inc_data)

        except ET.ParseError as e:
            print(f"CAP XML parse error: {e}")

        return incidents

    def _get_text(self, element, path: str, namespaces: dict = None) -> Optional[str]:
        """Safely get text from XML element"""
        if namespaces:
            child = element.find(path, namespaces)
        else:
            child = element.find(path)
        return child.text if child is not None else None

    def _get_float(self, element, path: str) -> Optional[float]:
        """Safely get float from XML element"""
        text = self._get_text(element, path)
        if text:
            try:
                return float(text)
            except ValueError:
                return None
        return None

    async def update_incidents(self, db: AsyncSession):
        """Update local incidents with CFS data"""
        # Fetch current incidents
        cfs_incidents = await self.fetch_current_incidents()

        if not cfs_incidents:
            return

        # Get CFS agency
        result = await db.execute(
            select(Agency).where(Agency.code == 'CFS')
        )
        cfs_agency = result.scalar_one_or_none()

        if not cfs_agency:
            return

        for cfs_inc in cfs_incidents:
            inc_num = cfs_inc.get('incident_number')
            if not inc_num:
                continue

            # Find matching incident in database
            # Try to match by incident number and today's date
            today = datetime.utcnow().date()

            result = await db.execute(
                select(Incident).where(
                    and_(
                        Incident.incident_number == inc_num,
                        Incident.agency_id == cfs_agency.id
                    )
                ).order_by(Incident.created_at.desc())
            )
            incident = result.scalar_one_or_none()

            if incident:
                # Update with CFS data
                if cfs_inc.get('status'):
                    incident.cfs_status = cfs_inc['status']
                    if cfs_inc['status'].lower() in ['closed', 'safe']:
                        incident.status = 'closed'
                        incident.closed_at = datetime.utcnow()

                if cfs_inc.get('latitude') and cfs_inc.get('longitude'):
                    # CFS provides authoritative location
                    incident.latitude = cfs_inc['latitude']
                    incident.longitude = cfs_inc['longitude']
                    incident.geocode_success = True
                    incident.geocode_attempted = True

                if cfs_inc.get('location'):
                    incident.address = cfs_inc['location']

                if cfs_inc.get('suburb'):
                    incident.suburb = cfs_inc['suburb']

                incident.cfs_last_update = datetime.utcnow()

        await db.commit()

    async def get_incident_status(
        self,
        incident_number: str
    ) -> Optional[Dict]:
        """Get status for a specific incident from CFS feed"""
        incidents = await self.fetch_current_incidents()

        for inc in incidents:
            if inc.get('incident_number') == incident_number:
                return inc

        return None
