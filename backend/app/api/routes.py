from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import json

from app.models.database import get_db
from app.models.models import Message, Incident, Agency, PowerOutage
from app.services.parser import MessageParser
from app.services.incident_service import IncidentService
from app.services.message_combiner import get_message_combiner
from app.services.event_manager import get_event_manager


router = APIRouter()
parser = MessageParser()
incident_service = IncidentService()
message_combiner = get_message_combiner()


# Request/Response Models
class MessageInput(BaseModel):
    """Raw message from collector"""
    message: str
    collector_id: str = "pager1"
    timestamp: Optional[datetime] = None


class BatchMessageInput(BaseModel):
    """Batch of messages from collector"""
    messages: List[str]
    collector_id: str = "pager1"


class UnitResponse(BaseModel):
    callsign: str
    status: str
    dispatched_at: Optional[datetime]

    class Config:
        from_attributes = True


class IncidentMessageResponse(BaseModel):
    id: int
    raw_message: str
    timestamp: datetime
    callsign: Optional[str]
    message_type: Optional[str]

    class Config:
        from_attributes = True


class IncidentResponse(BaseModel):
    id: int
    unique_id: str
    incident_number: str
    incident_date: datetime
    incident_type: Optional[str]
    alarm_level: Optional[int]
    priority: Optional[int]
    status: str
    address: Optional[str]
    suburb: Optional[str]
    map_reference: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    location_source: Optional[str]
    location_confidence: Optional[float]
    cfs_resources: Optional[int]
    cfs_description: Optional[str]
    agency_code: Optional[str]
    agency_name: Optional[str]
    agency_color: Optional[str]
    units: List[UnitResponse]
    messages: List[IncidentMessageResponse] = []
    created_at: datetime
    updated_at: datetime
    # Power outage detail (SAPN incidents only; None for everything else)
    outage: Optional["OutageDetail"] = None

    class Config:
        from_attributes = True


class OutageSuburb(BaseModel):
    name: Optional[str] = None
    postcode: Optional[str] = None


class OutageDetail(BaseModel):
    """SA Power Networks outage detail attached to a SAPN incident."""
    job_id: str
    is_planned: bool
    reason: Optional[str]
    status_text: Optional[str]
    affected_customers: Optional[int]
    primary_suburb: Optional[str]
    suburbs: List[OutageSuburb] = []
    start_time: Optional[datetime]
    estimated_restoration: Optional[datetime]
    active: bool


def _outage_detail(po: PowerOutage) -> OutageDetail:
    """Convert a PowerOutage ORM object to an OutageDetail (without heavy geometry)."""
    try:
        suburbs = json.loads(po.suburbs) if po.suburbs else []
    except (ValueError, TypeError):
        suburbs = []
    return OutageDetail(
        job_id=po.job_id,
        is_planned=bool(po.is_planned),
        reason=po.reason,
        status_text=po.status_text,
        affected_customers=po.affected_customers,
        primary_suburb=po.primary_suburb,
        suburbs=[OutageSuburb(name=s.get("name"), postcode=s.get("postcode")) for s in suburbs],
        start_time=po.start_time,
        estimated_restoration=po.estimated_restoration,
        active=bool(po.active),
    )


class MapIncidentResponse(BaseModel):
    """Lightweight incident response for map markers."""
    id: int
    latitude: float
    longitude: float
    agency_code: Optional[str]
    agency_color: Optional[str]
    incident_type: Optional[str]
    alarm_level: Optional[int]
    status: str
    address: Optional[str]
    suburb: Optional[str]
    location_source: Optional[str]
    incident_number: str
    incident_date: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    raw_message: str
    timestamp: datetime
    agency: Optional[str]
    callsign: Optional[str]
    priority: Optional[int]
    incident_type: Optional[str]
    message_type: Optional[str]

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total_incidents_24h: int
    active_incidents: int
    by_agency: dict


# Collector Endpoints
@router.post("/collector/message")
async def receive_message(
    input: MessageInput,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive a single pager message from collector.
    This is the primary endpoint for Raspberry Pi collectors.
    Multi-part messages are automatically combined before parsing.
    """
    try:
        # Process through message combiner to handle multi-part messages
        processed_message, was_combined = message_combiner.process(input.message)

        # If this was Part 1, it's been buffered - wait for Part 2
        if processed_message is None:
            return {
                "status": "buffered",
                "reason": "Part 1 of multi-part message buffered, awaiting Part 2"
            }

        parsed = parser.parse(processed_message)
        if not parsed:
            return {"status": "skipped", "reason": "unparseable or ignored message"}

        message = await incident_service.process_message(db, parsed)

        # Broadcast SSE event for new message
        event_manager = get_event_manager()
        await event_manager.broadcast("new_message", {
            "message_id": message.id if message else None,
            "incident_id": message.incident_id if message else None,
            "agency": parsed.agency,
            "type": parsed.message_type,
            "timestamp": datetime.utcnow().isoformat()
        })

        return {
            "status": "success",
            "message_id": message.id if message else None,
            "agency": parsed.agency,
            "type": parsed.message_type,
            "combined": was_combined
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collector/batch")
async def receive_batch(
    input: BatchMessageInput,
    db: AsyncSession = Depends(get_db)
):
    """
    Receive a batch of messages from collector.
    For initial sync or catch-up scenarios.
    Multi-part messages are automatically combined before parsing.
    """
    processed = 0
    skipped = 0
    buffered = 0
    combined = 0

    # Use a local combiner for batch processing to ensure proper ordering
    from app.services.message_combiner import MessageCombiner
    batch_combiner = MessageCombiner()

    for msg in input.messages:
        try:
            # Process through combiner for multi-part handling
            processed_message, was_combined = batch_combiner.process(msg)

            if processed_message is None:
                # Part 1 buffered, waiting for Part 2
                buffered += 1
                continue

            if was_combined:
                combined += 1

            parsed = parser.parse(processed_message)
            if parsed:
                await incident_service.process_message(db, parsed)
                processed += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    # Process any remaining buffered Part 1 messages that didn't get a Part 2
    remaining = batch_combiner.flush_pending()
    for msg in remaining:
        try:
            parsed = parser.parse(msg)
            if parsed:
                await incident_service.process_message(db, parsed)
                processed += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    # Broadcast SSE event for batch completion
    if processed > 0:
        event_manager = get_event_manager()
        await event_manager.broadcast("batch_processed", {
            "processed": processed,
            "skipped": skipped,
            "combined": combined,
            "timestamp": datetime.utcnow().isoformat()
        })

    return {
        "status": "success",
        "processed": processed,
        "skipped": skipped,
        "combined": combined
    }


IncidentResponse.model_rebuild()  # resolve the forward reference to OutageDetail


def _incident_to_response(inc: Incident) -> IncidentResponse:
    """Convert an Incident ORM object to an IncidentResponse"""
    priority = None
    if inc.messages:
        for msg in inc.messages:
            if msg.priority is not None:
                priority = msg.priority
                break

    return IncidentResponse(
        id=inc.id,
        unique_id=inc.unique_id,
        incident_number=inc.incident_number,
        incident_date=inc.incident_date,
        incident_type=inc.incident_type,
        alarm_level=inc.alarm_level,
        priority=priority,
        status=inc.status,
        address=inc.address,
        suburb=inc.suburb,
        map_reference=inc.map_reference,
        latitude=inc.latitude,
        longitude=inc.longitude,
        location_source=inc.location_source,
        location_confidence=inc.location_confidence,
        cfs_resources=inc.cfs_resources,
        cfs_description=inc.cfs_description,
        agency_code=inc.agency.code if inc.agency else None,
        agency_name=inc.agency.name if inc.agency else None,
        agency_color=inc.agency.color if inc.agency else None,
        units=[UnitResponse(
            callsign=u.callsign,
            status=u.status,
            dispatched_at=u.dispatched_at
        ) for u in inc.units],
        messages=[IncidentMessageResponse(
            id=m.id,
            raw_message=m.raw_message,
            timestamp=m.timestamp,
            callsign=m.callsign,
            message_type=m.message_type
        ) for m in inc.messages],
        created_at=inc.created_at,
        updated_at=inc.updated_at,
        outage=_outage_detail(inc.power_outage) if inc.power_outage else None,
    )


# Frontend API Endpoints
@router.get("/incidents", response_model=List[IncidentResponse])
async def get_incidents(
    agency: Optional[str] = Query(None, description="Filter by agency code"),
    hours: int = Query(168, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Get recent incidents for display"""
    incidents = await incident_service.get_recent_incidents(
        db, hours=hours, agency_code=agency, limit=limit, offset=offset
    )
    return [_incident_to_response(inc) for inc in incidents]


@router.get("/incidents/search", response_model=List[IncidentResponse])
async def search_incidents(
    q: str = Query(..., min_length=1, description="Search query"),
    agency: Optional[str] = Query(None, description="Filter by agency code"),
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Search incidents across the entire database"""
    incidents = await incident_service.search_incidents(
        db, query_text=q, agency_code=agency, limit=limit, offset=offset
    )
    return [_incident_to_response(inc) for inc in incidents]


@router.get("/incidents/map", response_model=List[MapIncidentResponse])
async def get_map_incidents(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    agency: Optional[str] = Query(None, description="Filter by agency code"),
    db: AsyncSession = Depends(get_db)
):
    """Get incidents with coordinates for map display (lightweight payload)."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = (
        select(Incident)
        .options(selectinload(Incident.agency))
        .where(
            Incident.created_at >= cutoff,
            Incident.latitude.isnot(None),
            Incident.longitude.isnot(None),
            Incident.status != 'closed',
            # SAPN outages render as affected-area polygons via /api/outages, not points
            ~Incident.agency.has(Agency.code == 'SAPN'),
        )
        .order_by(Incident.created_at.desc())
        .limit(500)
    )

    if agency:
        query = query.join(Agency).where(Agency.code == agency)

    result = await db.execute(query)
    incidents = result.scalars().all()

    return [MapIncidentResponse(
        id=inc.id,
        latitude=inc.latitude,
        longitude=inc.longitude,
        agency_code=inc.agency.code if inc.agency else None,
        agency_color=inc.agency.color if inc.agency else None,
        incident_type=inc.incident_type,
        alarm_level=inc.alarm_level,
        status=inc.status,
        address=inc.address,
        suburb=inc.suburb,
        location_source=inc.location_source,
        incident_number=inc.incident_number,
        incident_date=inc.incident_date,
    ) for inc in incidents]


class OutageAreaResponse(BaseModel):
    """Power outage with its affected-area polygon, for map rendering."""
    job_id: str
    incident_id: Optional[int]
    is_planned: bool
    reason: Optional[str]
    status_text: Optional[str]
    affected_customers: Optional[int]
    primary_suburb: Optional[str]
    estimated_restoration: Optional[datetime]
    centroid_lat: Optional[float]
    centroid_lng: Optional[float]
    geometry: List[List[float]]  # [[lng, lat], ...]


@router.get("/outages", response_model=List[OutageAreaResponse])
async def get_outages(db: AsyncSession = Depends(get_db)):
    """Get active SA Power Networks outages with affected-area polygons (for the map)."""
    result = await db.execute(
        select(PowerOutage).where(PowerOutage.active == True)  # noqa: E712
    )
    outages = result.scalars().all()

    responses = []
    for po in outages:
        try:
            geometry = json.loads(po.geometry) if po.geometry else []
        except (ValueError, TypeError):
            geometry = []
        responses.append(OutageAreaResponse(
            job_id=po.job_id,
            incident_id=po.incident_id,
            is_planned=bool(po.is_planned),
            reason=po.reason,
            status_text=po.status_text,
            affected_customers=po.affected_customers,
            primary_suburb=po.primary_suburb,
            estimated_restoration=po.estimated_restoration,
            centroid_lat=po.centroid_lat,
            centroid_lng=po.centroid_lng,
            geometry=geometry,
        ))
    return responses


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get a single incident by ID"""
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.agency))
        .options(selectinload(Incident.units))
        .options(selectinload(Incident.messages))
        .options(selectinload(Incident.power_outage))
        .where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return _incident_to_response(incident)


@router.get("/messages", response_model=List[MessageResponse])
async def get_messages(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get recent raw messages"""
    result = await db.execute(
        select(Message)
        .options(selectinload(Message.agency))
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return [MessageResponse(
        id=m.id,
        raw_message=m.raw_message,
        timestamp=m.timestamp,
        agency=m.agency.code if m.agency else None,
        callsign=m.callsign,
        priority=m.priority,
        incident_type=m.incident_type,
        message_type=m.message_type
    ) for m in messages]


class RawMessageResponse(BaseModel):
    id: int
    message: str  # Raw message with FLEX prefix stripped
    timestamp: datetime

    class Config:
        from_attributes = True


def strip_flex_prefix(raw_message: str) -> str:
    """
    Strip the FLEX prefix from a raw pager message.
    Example input: FLEX|2026-01-26 05:08:06|1600/2/K/A|02.003|001933169|ALN|C82 PR: 2...
    Example output: C82 PR: 2...
    """
    import re
    # Match FLEX|timestamp|mode|frame|capcode|type| prefix pattern
    pattern = r'^FLEX\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|'
    return re.sub(pattern, '', raw_message)


@router.get("/messages/raw", response_model=List[RawMessageResponse])
async def get_raw_messages(
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent raw messages with FLEX prefix stripped.
    Returns all messages without any parsing or filtering,
    just the raw content after removing the FLEX header.
    """
    result = await db.execute(
        select(Message)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return [RawMessageResponse(
        id=m.id,
        message=strip_flex_prefix(m.raw_message),
        timestamp=m.timestamp
    ) for m in messages]


@router.get("/config")
async def get_frontend_config():
    """Get frontend configuration (Mapbox token, etc.)."""
    from app.core.config import get_settings
    settings = get_settings()
    return {
        "mapbox_token": settings.mapbox_token,
    }


@router.get("/agencies")
async def get_agencies(db: AsyncSession = Depends(get_db)):
    """Get all agencies with their colors"""
    result = await db.execute(select(Agency))
    agencies = result.scalars().all()

    # Filter out MedStar and UNKNOWN agencies
    excluded = {'MedStar', 'UNKNOWN'}
    return [{"code": a.code, "name": a.name, "color": a.color} for a in agencies if a.code not in excluded]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    from app.utils.timezone import get_adelaide_midnight_utc

    cutoff_24h = get_adelaide_midnight_utc()

    # Count incidents in last 24 hours
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.agency))
        .where(Incident.created_at >= cutoff_24h)
    )
    incidents = result.scalars().all()

    active = sum(1 for i in incidents if i.status == 'active')

    # Group by agency
    by_agency = {}
    for inc in incidents:
        code = inc.agency.code if inc.agency else 'UNKNOWN'
        by_agency[code] = by_agency.get(code, 0) + 1

    return StatsResponse(
        total_incidents_24h=len(incidents),
        active_incidents=active,
        by_agency=by_agency
    )


# Health check
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# Server-Sent Events endpoint
@router.get("/events")
async def event_stream(request: Request):
    """
    Server-Sent Events endpoint for real-time updates.
    Clients connect here to receive push notifications for new incidents and messages.
    """
    event_manager = get_event_manager()

    async def event_generator():
        async for event in event_manager.subscribe():
            if await request.is_disconnected():
                break
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Content-Encoding": "none",  # Prevent compression interfering with SSE
            "Transfer-Encoding": "chunked",  # Explicit chunked encoding
        }
    )
