"""
Integration with the SA Power Networks (SAPN) public outages feed.

Polls `GET {sapn_base_url}/Outages/GetPublicisedCurrentOutages/` every 5 minutes.
Each current outage is mirrored into an Incident (agency SAPN) so it appears in the
normal job/list feed, filter menu and detail modal, while a companion PowerOutage
row holds the outage-specific detail (restoration time, affected customers,
planned/unplanned flag) and the polygon of the affected area for the map.

Outages that drop out of the feed (power restored) are marked closed but retained
so the list keeps recent history, matching how emergency incidents behave.
"""

import json
from datetime import datetime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.models import Incident, Agency, PowerOutage
from app.services.event_manager import get_event_manager

settings = get_settings()

ADELAIDE_TZ = ZoneInfo("Australia/Adelaide")
UTC = ZoneInfo("UTC")

OUTAGES_PATH = "/Outages/GetPublicisedCurrentOutages/"


def _adelaide_to_utc(value: Optional[str]) -> Optional[datetime]:
    """Convert a naive Adelaide-local ISO timestamp from the feed to naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ADELAIDE_TZ)
    return dt.astimezone(UTC).replace(tzinfo=None)


def _centroid(geometry: List[Dict]) -> Optional[tuple]:
    """Average lat/lng of the polygon points, used for the marker/label position."""
    pts = [(p.get("lat"), p.get("lng")) for p in geometry
           if p.get("lat") is not None and p.get("lng") is not None]
    if not pts:
        return None
    lat = sum(p[0] for p in pts) / len(pts)
    lng = sum(p[1] for p in pts) / len(pts)
    return lat, lng


class SAPNOutageService:
    """Fetches SAPN outages and syncs them into incidents + power_outages."""

    async def fetch_outages(self) -> List[Dict]:
        """Fetch the current outages list from the SAPN feed."""
        url = settings.sapn_base_url.rstrip("/") + OUTAGES_PATH
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
                if response.status_code != 200:
                    print(f"Failed to fetch SAPN outages: {response.status_code}")
                    return []
                data = response.json()
                return data.get("currentOutages", []) or []
        except Exception as e:
            print(f"Error fetching SAPN outages: {e}")
            return []

    async def process_outages(self, db: AsyncSession) -> int:
        """
        Fetch outages and upsert incidents + power_outages. Close outages that have
        dropped out of the feed. Returns the number of newly created outages.
        """
        outages = await self.fetch_outages()

        # Get (or create) the SAPN agency.
        result = await db.execute(select(Agency).where(Agency.code == "SAPN"))
        agency = result.scalar_one_or_none()
        if not agency:
            print("SAPN agency not found in database; skipping outage sync")
            return 0

        # Load all existing SAPN outages (keyed by job_id) with their incidents.
        result = await db.execute(
            select(PowerOutage).options(selectinload(PowerOutage.incident))
        )
        existing = {po.job_id: po for po in result.scalars().all()}

        seen_job_ids = set()
        new_count = 0
        now = datetime.utcnow()

        for outage in outages:
            job_id = str(outage.get("jobID") or "").strip()
            if not job_id:
                continue
            seen_job_ids.add(job_id)

            suburbs = outage.get("affectedSuburbs") or []
            primary_suburb = suburbs[0].get("name") if suburbs else None
            geometry = outage.get("geometry") or []
            centroid = _centroid(geometry)
            reason = outage.get("reason") or "Power outage"
            start_utc = _adelaide_to_utc(outage.get("startDateTime"))
            restoration_utc = _adelaide_to_utc(outage.get("estimatedRestoration"))
            # Store geometry as GeoJSON-order [lng, lat] pairs for the frontend.
            geometry_lnglat = [
                [p["lng"], p["lat"]] for p in geometry
                if p.get("lat") is not None and p.get("lng") is not None
            ]

            po = existing.get(job_id)
            if po is None:
                # New outage -> create incident + power_outage.
                incident = Incident(
                    unique_id=f"SAPN_{job_id}",
                    agency_id=agency.id,
                    incident_number=job_id,
                    incident_date=start_utc or now,
                    incident_type=reason,
                    status="active",
                    suburb=primary_suburb,
                    latitude=centroid[0] if centroid else None,
                    longitude=centroid[1] if centroid else None,
                    location_source="OFFICIAL_FEED",
                    geocode_attempted=True,
                    geocode_success=centroid is not None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(incident)
                await db.flush()  # assign incident.id

                po = PowerOutage(job_id=job_id, incident_id=incident.id)
                db.add(po)
                new_count += 1
            else:
                # Existing outage -> refresh detail and reactivate if it had closed.
                incident = po.incident
                if incident is not None:
                    incident.incident_type = reason
                    incident.suburb = primary_suburb
                    if centroid:
                        incident.latitude = centroid[0]
                        incident.longitude = centroid[1]
                    if incident.status != "active":
                        incident.status = "active"
                        incident.closed_at = None
                    incident.updated_at = now

            # Update the shared outage detail fields.
            po.is_planned = bool(outage.get("isPaw"))
            po.reason = reason
            po.status_text = outage.get("status")
            po.affected_customers = outage.get("affectedCustomers")
            po.primary_suburb = primary_suburb
            po.suburbs = json.dumps(suburbs)
            po.geometry = json.dumps(geometry_lnglat)
            po.centroid_lat = centroid[0] if centroid else None
            po.centroid_lng = centroid[1] if centroid else None
            po.start_time = start_utc
            po.estimated_restoration = restoration_utc
            po.active = True
            po.updated_at = now

        # Close outages that are no longer in the feed (power restored).
        for job_id, po in existing.items():
            if job_id not in seen_job_ids and po.active:
                po.active = False
                po.updated_at = now
                if po.incident is not None and po.incident.status != "closed":
                    po.incident.status = "closed"
                    po.incident.closed_at = now

        await db.commit()

        if new_count > 0:
            # Data is already committed; a notification failure must not discard it.
            try:
                event_manager = get_event_manager()
                await event_manager.broadcast("new_message", {
                    "message_id": None,
                    "incident_id": None,
                    "agency": "SAPN",
                    "type": "power_outage",
                    "timestamp": now.isoformat(),
                })
            except Exception as e:
                print(f"SAPN: outage sync committed but SSE broadcast failed: {e}")

        return new_count


_sapn_service: Optional[SAPNOutageService] = None


def get_sapn_service() -> SAPNOutageService:
    global _sapn_service
    if _sapn_service is None:
        _sapn_service = SAPNOutageService()
    return _sapn_service
