"""
Waze Traffic Incident Integration Service

Fetches traffic incidents from the Waze Partner Hub API and creates
incidents in the database for display on the frontend.
"""

from datetime import datetime
from typing import List, Dict, Optional, Set
import math
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Incident, Agency
from app.services.event_manager import get_event_manager


# Waze feed URL
WAZE_FEED_URL = "https://www.waze.com/row-partnerhub-api/partners/11378695718/waze-feeds/3618df7b-846d-4101-937a-d6cf21951e72?format=1"

# Event types to exclude
EXCLUDED_TYPES = {'ROAD_CLOSED'}


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points in meters using Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of first point
        lat2, lon2: Latitude and longitude of second point

    Returns:
        float: Distance in meters
    """
    R = 6371000  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) *
         math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


class WazeService:
    """Service for fetching and processing Waze traffic incidents"""

    def __init__(self):
        # Track seen UUIDs to avoid duplicates within a session
        self._seen_uuids: Set[str] = set()

    def normalize_subtype(self, subtype: str) -> str:
        """
        Normalize Waze subtype to human-readable text.
        e.g., JAM_STAND_STILL_TRAFFIC -> Jam Stand Still Traffic
        """
        if not subtype:
            return "Unknown"
        # Remove underscores and title case
        return subtype.replace('_', ' ').title()

    def normalize_type(self, event_type: str, subtype: str) -> str:
        """
        Create a readable incident type from type and subtype.
        """
        if subtype:
            return self.normalize_subtype(subtype)
        if event_type:
            return event_type.replace('_', ' ').title()
        return "Traffic Incident"

    async def fetch_alerts(self) -> List[Dict]:
        """Fetch current alerts from Waze API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(WAZE_FEED_URL)

                if response.status_code != 200:
                    print(f"Failed to fetch Waze feed: {response.status_code}")
                    return []

                data = response.json()
                alerts = data.get('alerts', [])

                # Filter out excluded types
                filtered = [
                    alert for alert in alerts
                    if alert.get('type') not in EXCLUDED_TYPES
                ]

                return filtered

        except Exception as e:
            print(f"Error fetching Waze feed: {e}")
            return []

    def generate_unique_id(self, uuid: str, pub_millis: int) -> str:
        """
        Generate unique incident identifier for Waze incidents.
        Format: WAZE_UUID_YYYYMMDD
        """
        # Convert pubMillis to date
        pub_date = datetime.fromtimestamp(pub_millis / 1000)
        date_str = pub_date.strftime('%Y%m%d')
        # Use first 8 chars of UUID for brevity
        short_uuid = uuid[:8] if uuid else 'unknown'
        return f"WAZE_{short_uuid}_{date_str}"

    async def process_alerts(self, db: AsyncSession) -> int:
        """
        Fetch Waze alerts and create/update incidents with deduplication.
        Skips incidents that are the same type and within 200m of existing incidents.
        Returns number of new incidents created.
        """
        alerts = await self.fetch_alerts()

        if not alerts:
            return 0

        # Get WAZE agency
        result = await db.execute(
            select(Agency).where(Agency.code == 'WAZE')
        )
        waze_agency = result.scalar_one_or_none()

        if not waze_agency:
            print("WAZE agency not found in database")
            return 0

        # Fetch existing active Waze incidents for deduplication
        result = await db.execute(
            select(Incident).where(
                Incident.agency_id == waze_agency.id,
                Incident.status == 'active'
            )
        )
        existing_incidents = result.scalars().all()

        new_count = 0
        event_manager = get_event_manager()

        for alert in alerts:
            try:
                uuid = alert.get('uuid')
                if not uuid:
                    continue

                pub_millis = alert.get('pubMillis', 0)
                unique_id = self.generate_unique_id(uuid, pub_millis)

                # Check if exact incident already exists by unique_id
                if any(inc.unique_id == unique_id for inc in existing_incidents):
                    continue

                # Extract location
                location = alert.get('location', {})
                longitude = location.get('x')
                latitude = location.get('y')

                # Get street and city
                street = alert.get('street', '')
                city = alert.get('city', '')

                # Build address
                address = street if street else None

                # Create incident type from type/subtype
                event_type = alert.get('type', '')
                subtype = alert.get('subtype', '')
                incident_type = self.normalize_type(event_type, subtype)

                # Check for duplicates within 200m of same type
                if latitude and longitude:
                    is_duplicate = False
                    for existing in existing_incidents:
                        # Must have coordinates
                        if not (existing.latitude and existing.longitude):
                            continue

                        # Must be same incident type
                        if existing.incident_type != incident_type:
                            continue

                        # Check distance
                        distance = haversine_distance(
                            latitude, longitude,
                            existing.latitude, existing.longitude
                        )

                        if distance <= 200:  # Within 200 meters
                            is_duplicate = True
                            print(f"Waze: Skipping duplicate {incident_type} at {distance:.0f}m from existing")
                            break

                    if is_duplicate:
                        continue

                # Create incident timestamp
                incident_date = datetime.fromtimestamp(pub_millis / 1000) if pub_millis else datetime.utcnow()

                # Create new incident
                incident = Incident(
                    unique_id=unique_id,
                    agency_id=waze_agency.id,
                    incident_number=uuid[:8].upper(),
                    incident_date=incident_date,
                    incident_type=incident_type,
                    address=address,
                    suburb=city if city else None,
                    latitude=latitude,
                    longitude=longitude,
                    status='active',
                    geocode_success=True if latitude and longitude else False,
                    geocode_attempted=True
                )

                db.add(incident)
                existing_incidents.append(incident)  # Add to local list for next iteration
                new_count += 1

                # Track this UUID
                self._seen_uuids.add(uuid)

            except Exception as e:
                print(f"Error processing Waze alert: {e}")
                continue

        if new_count > 0:
            await db.commit()

            # Broadcast SSE event for new incidents
            await event_manager.broadcast("new_message", {
                "source": "waze",
                "count": new_count,
                "timestamp": datetime.utcnow().isoformat()
            })

        return new_count

    async def cleanup_old_alerts(self, db: AsyncSession):
        """
        Mark Waze incidents as closed if they're no longer in the feed.
        This helps indicate when traffic conditions have cleared.
        """
        # Fetch current alerts
        alerts = await self.fetch_alerts()
        current_uuids = {alert.get('uuid') for alert in alerts if alert.get('uuid')}

        # Get WAZE agency
        result = await db.execute(
            select(Agency).where(Agency.code == 'WAZE')
        )
        waze_agency = result.scalar_one_or_none()

        if not waze_agency:
            return

        # Find active Waze incidents
        result = await db.execute(
            select(Incident).where(
                Incident.agency_id == waze_agency.id,
                Incident.status == 'active'
            )
        )
        active_incidents = result.scalars().all()

        for incident in active_incidents:
            # Extract UUID from unique_id (WAZE_UUID_DATE)
            parts = incident.unique_id.split('_')
            if len(parts) >= 2:
                inc_uuid_prefix = parts[1]
                # Check if any current alert starts with this prefix
                still_active = any(
                    uuid.startswith(inc_uuid_prefix)
                    for uuid in current_uuids
                )
                if not still_active:
                    incident.status = 'closed'
                    incident.closed_at = datetime.utcnow()

        await db.commit()


# Singleton instance
_waze_service: Optional[WazeService] = None


def get_waze_service() -> WazeService:
    """Get singleton WazeService instance"""
    global _waze_service
    if _waze_service is None:
        _waze_service = WazeService()
    return _waze_service
