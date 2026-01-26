from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Message, Incident, IncidentUnit, Agency
from app.services.parser import ParsedMessage


class IncidentService:
    """Service for managing incidents"""

    # Agency codes and colors (pastel)
    AGENCY_CONFIG = {
        'SAAS': {'name': 'SA Ambulance Service', 'color': '#C8E6C9'},  # Light green
        'CFS': {'name': 'Country Fire Service', 'color': '#FFCCBC'},   # Light orange
        'MFS': {'name': 'Metropolitan Fire Service', 'color': '#FFCDD2'},  # Light red
        'SES': {'name': 'State Emergency Service', 'color': '#FFF9C4'},  # Light yellow
        'MedStar': {'name': 'MedSTAR', 'color': '#E1BEE7'},  # Light purple
        'TMC': {'name': 'Transport Management Centre', 'color': '#B3E5FC'},  # Light blue
        'UNKNOWN': {'name': 'Unknown', 'color': '#E0E0E0'},  # Light gray
    }

    async def ensure_agencies(self, db: AsyncSession):
        """Ensure all agencies exist in the database"""
        for code, config in self.AGENCY_CONFIG.items():
            result = await db.execute(
                select(Agency).where(Agency.code == code)
            )
            agency = result.scalar_one_or_none()
            if not agency:
                agency = Agency(
                    code=code,
                    name=config['name'],
                    color=config['color']
                )
                db.add(agency)
        await db.commit()

    async def get_agency(self, db: AsyncSession, code: str) -> Optional[Agency]:
        """Get agency by code"""
        result = await db.execute(
            select(Agency).where(Agency.code == code)
        )
        return result.scalar_one_or_none()

    def generate_unique_id(
        self,
        agency_code: str,
        incident_number: str,
        incident_date: datetime
    ) -> str:
        """
        Generate unique incident identifier.
        Format: AGENCY_INCIDENTNUM_YYYYMMDD
        """
        date_str = incident_date.strftime('%Y%m%d')
        # Normalize incident number
        inc_num = incident_number.upper().replace(':', '').replace(' ', '')
        return f"{agency_code}_{inc_num}_{date_str}"

    async def process_message(
        self,
        db: AsyncSession,
        parsed: ParsedMessage
    ) -> Optional[Message]:
        """
        Process a parsed message:
        - Create message record
        - Create or update incident
        - Track units
        """
        if not parsed:
            return None

        # Get agency
        agency = await self.get_agency(db, parsed.agency or 'UNKNOWN')
        if not agency:
            await self.ensure_agencies(db)
            agency = await self.get_agency(db, parsed.agency or 'UNKNOWN')

        # Create message record
        message = Message(
            raw_message=parsed.raw_message,
            timestamp=parsed.timestamp,
            received_at=datetime.utcnow(),
            flex_speed=parsed.flex_speed,
            flex_frame=parsed.flex_frame,
            capcode=parsed.capcode,
            agency_id=agency.id if agency else None,
            callsign=parsed.callsign,
            priority=parsed.priority,
            location_text=parsed.location_text,
            map_reference=parsed.map_reference,
            job_id=parsed.job_id or parsed.incident_number,
            dispatch_time=parsed.dispatch_time,
            incident_type=parsed.incident_type,
            message_type=parsed.message_type
        )

        # Find or create incident if this is a dispatch message
        if parsed.message_type == 'dispatch' and (parsed.job_id or parsed.incident_number):
            incident = await self._get_or_create_incident(
                db, parsed, agency
            )
            if incident:
                message.incident_id = incident.id

                # Add unit to incident
                if parsed.callsign:
                    await self._add_unit_to_incident(
                        db, incident, parsed.callsign, parsed.timestamp
                    )

                # Add units from units_paged list (for CFS/MFS incidents)
                if parsed.units_paged:
                    for unit_callsign in parsed.units_paged:
                        await self._add_unit_to_incident(
                            db, incident, unit_callsign, parsed.timestamp
                        )

        db.add(message)
        await db.commit()
        await db.refresh(message)

        return message

    async def _get_or_create_incident(
        self,
        db: AsyncSession,
        parsed: ParsedMessage,
        agency: Optional[Agency]
    ) -> Optional[Incident]:
        """Get existing incident or create new one"""
        inc_number = parsed.incident_number or parsed.job_id
        if not inc_number:
            return None

        # Generate unique ID
        unique_id = self.generate_unique_id(
            parsed.agency or 'UNKNOWN',
            inc_number,
            parsed.timestamp
        )

        # Try to find existing incident
        result = await db.execute(
            select(Incident).where(Incident.unique_id == unique_id)
        )
        incident = result.scalar_one_or_none()

        if incident:
            # Update if new information available
            if parsed.incident_type and not incident.incident_type:
                incident.incident_type = parsed.incident_type
            if parsed.alarm_level and not incident.alarm_level:
                incident.alarm_level = parsed.alarm_level
            incident.updated_at = datetime.utcnow()
            await db.commit()
            return incident

        # Create new incident
        # Build address from location_text and suburb
        address = None
        if parsed.location_text:
            address = parsed.location_text
            if parsed.suburb and parsed.suburb not in parsed.location_text:
                address = f"{parsed.location_text}, {parsed.suburb}"

        incident = Incident(
            unique_id=unique_id,
            agency_id=agency.id if agency else None,
            incident_number=inc_number,
            incident_date=parsed.timestamp,
            incident_type=parsed.incident_type,
            alarm_level=parsed.alarm_level,
            address=address,
            suburb=parsed.suburb,
            map_reference=parsed.map_reference,
            status='active'
        )

        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        return incident

    async def _add_unit_to_incident(
        self,
        db: AsyncSession,
        incident: Incident,
        callsign: str,
        dispatch_time: datetime
    ):
        """Add a unit to an incident if not already assigned"""
        # Check if unit already assigned
        result = await db.execute(
            select(IncidentUnit).where(
                and_(
                    IncidentUnit.incident_id == incident.id,
                    IncidentUnit.callsign == callsign
                )
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            unit = IncidentUnit(
                incident_id=incident.id,
                callsign=callsign,
                dispatched_at=dispatch_time,
                status='dispatched'
            )
            db.add(unit)
            await db.commit()

    async def get_active_incidents(
        self,
        db: AsyncSession,
        agency_code: Optional[str] = None,
        limit: int = 100
    ) -> List[Incident]:
        """Get active incidents, optionally filtered by agency"""
        query = (
            select(Incident)
            .options(selectinload(Incident.agency))
            .options(selectinload(Incident.units))
            .options(selectinload(Incident.messages))
            .where(Incident.status == 'active')
            .order_by(Incident.created_at.desc())
            .limit(limit)
        )

        if agency_code:
            query = query.join(Agency).where(Agency.code == agency_code)

        result = await db.execute(query)
        return result.scalars().all()

    async def get_recent_incidents(
        self,
        db: AsyncSession,
        hours: int = 24,
        agency_code: Optional[str] = None,
        limit: int = 200
    ) -> List[Incident]:
        """Get incidents from the last N hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        query = (
            select(Incident)
            .options(selectinload(Incident.agency))
            .options(selectinload(Incident.units))
            .options(selectinload(Incident.messages))
            .where(Incident.created_at >= cutoff)
            .order_by(Incident.created_at.desc())
            .limit(limit)
        )

        if agency_code:
            query = query.join(Agency).where(Agency.code == agency_code)

        result = await db.execute(query)
        return result.scalars().all()

    async def cleanup_old_messages(
        self,
        db: AsyncSession,
        days: int = 30
    ):
        """Delete messages older than N days"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Delete old messages
        await db.execute(
            delete(Message).where(Message.timestamp < cutoff)
        )

        # Delete old incidents
        await db.execute(
            delete(Incident).where(Incident.incident_date < cutoff)
        )

        await db.commit()
