from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.database import get_db
from app.models.models import Message, Incident, Agency, IncidentUnit
from app.services.parser import MessageParser, ParsedMessage
from app.services.incident_service import IncidentService


router = APIRouter()
parser = MessageParser()
incident_service = IncidentService()


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


class IncidentResponse(BaseModel):
    id: int
    unique_id: str
    incident_number: str
    incident_date: datetime
    incident_type: Optional[str]
    alarm_level: Optional[int]
    status: str
    address: Optional[str]
    suburb: Optional[str]
    map_reference: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    agency_code: Optional[str]
    agency_name: Optional[str]
    agency_color: Optional[str]
    units: List[UnitResponse]
    created_at: datetime
    updated_at: datetime

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
    """
    try:
        parsed = parser.parse(input.message)
        if not parsed:
            return {"status": "skipped", "reason": "unparseable or ignored message"}

        message = await incident_service.process_message(db, parsed)

        return {
            "status": "success",
            "message_id": message.id if message else None,
            "agency": parsed.agency,
            "type": parsed.message_type
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
    """
    processed = 0
    skipped = 0

    for msg in input.messages:
        try:
            parsed = parser.parse(msg)
            if parsed:
                await incident_service.process_message(db, parsed)
                processed += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    return {
        "status": "success",
        "processed": processed,
        "skipped": skipped
    }


# Frontend API Endpoints
@router.get("/incidents", response_model=List[IncidentResponse])
async def get_incidents(
    agency: Optional[str] = Query(None, description="Filter by agency code"),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    """Get recent incidents for display"""
    incidents = await incident_service.get_recent_incidents(
        db, hours=hours, agency_code=agency, limit=limit
    )

    response = []
    for inc in incidents:
        response.append(IncidentResponse(
            id=inc.id,
            unique_id=inc.unique_id,
            incident_number=inc.incident_number,
            incident_date=inc.incident_date,
            incident_type=inc.incident_type,
            alarm_level=inc.alarm_level,
            status=inc.status,
            address=inc.address,
            suburb=inc.suburb,
            map_reference=inc.map_reference,
            latitude=inc.latitude,
            longitude=inc.longitude,
            agency_code=inc.agency.code if inc.agency else None,
            agency_name=inc.agency.name if inc.agency else None,
            agency_color=inc.agency.color if inc.agency else None,
            units=[UnitResponse(
                callsign=u.callsign,
                status=u.status,
                dispatched_at=u.dispatched_at
            ) for u in inc.units],
            created_at=inc.created_at,
            updated_at=inc.updated_at
        ))

    return response


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
        .where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()

    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return IncidentResponse(
        id=incident.id,
        unique_id=incident.unique_id,
        incident_number=incident.incident_number,
        incident_date=incident.incident_date,
        incident_type=incident.incident_type,
        alarm_level=incident.alarm_level,
        status=incident.status,
        address=incident.address,
        suburb=incident.suburb,
        map_reference=incident.map_reference,
        latitude=incident.latitude,
        longitude=incident.longitude,
        agency_code=incident.agency.code if incident.agency else None,
        agency_name=incident.agency.name if incident.agency else None,
        agency_color=incident.agency.color if incident.agency else None,
        units=[UnitResponse(
            callsign=u.callsign,
            status=u.status,
            dispatched_at=u.dispatched_at
        ) for u in incident.units],
        created_at=incident.created_at,
        updated_at=incident.updated_at
    )


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


@router.get("/agencies")
async def get_agencies(db: AsyncSession = Depends(get_db)):
    """Get all agencies with their colors"""
    result = await db.execute(select(Agency))
    agencies = result.scalars().all()

    return [{"code": a.code, "name": a.name, "color": a.color} for a in agencies]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics"""
    from datetime import timedelta

    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)

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
