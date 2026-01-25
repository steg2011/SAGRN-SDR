from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.database import Base


class Agency(Base):
    """Emergency service agencies (SAAS, CFS, MFS, SES, MedStar, TMC)"""
    __tablename__ = "agencies"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)  # SAAS, CFS, MFS, etc.
    name = Column(String(100), nullable=False)
    color = Column(String(7), default="#CCCCCC")  # Pastel hex color

    messages = relationship("Message", back_populates="agency")
    incidents = relationship("Incident", back_populates="agency")


class CapCode(Base):
    """Pager CAP codes lookup table"""
    __tablename__ = "capcodes"

    id = Column(Integer, primary_key=True, index=True)
    capcode = Column(String(20), unique=True, nullable=False, index=True)
    description = Column(String(200))
    agency_id = Column(Integer, ForeignKey("agencies.id"))
    unit_type = Column(String(50))  # Ambulance, Fire truck, etc.

    agency = relationship("Agency")


class JobType(Base):
    """SAAS job type abbreviations"""
    __tablename__ = "job_types"

    id = Column(Integer, primary_key=True, index=True)
    abbreviation = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    priority = Column(Integer)


class CrewAbbreviation(Base):
    """SAAS crew/unit abbreviations"""
    __tablename__ = "crew_abbreviations"

    id = Column(Integer, primary_key=True, index=True)
    abbreviation = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(100))
    unit_type = Column(String(50))  # Ambulance, Response, etc.


class Message(Base):
    """Raw pager messages"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    raw_message = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)
    collector_id = Column(String(50), default="pager1")

    # FLEX protocol fields
    flex_speed = Column(String(20))
    flex_frame = Column(String(20))
    capcode = Column(String(20), index=True)

    # Parsed fields
    agency_id = Column(Integer, ForeignKey("agencies.id"), index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), index=True)
    callsign = Column(String(20), index=True)
    priority = Column(Integer)
    location_text = Column(String(200))
    map_reference = Column(String(50))
    job_id = Column(String(20), index=True)  # D01026, INC0091, S0030, etc.
    dispatch_time = Column(String(10))
    incident_type = Column(String(100))

    # Message classification
    message_type = Column(String(50))  # dispatch, update, stand_down, info, etc.
    is_duplicate = Column(Boolean, default=False)

    agency = relationship("Agency", back_populates="messages")
    incident = relationship("Incident", back_populates="messages")

    __table_args__ = (
        Index('ix_messages_timestamp_agency', 'timestamp', 'agency_id'),
        Index('ix_messages_job_date', 'job_id', 'timestamp'),
    )


class Incident(Base):
    """Grouped incidents with unique identifiers"""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String(50), unique=True, nullable=False, index=True)  # CFS_INC0091_20260125
    agency_id = Column(Integer, ForeignKey("agencies.id"), index=True)
    incident_number = Column(String(20), nullable=False)  # INC0091, D01026, etc.
    incident_date = Column(DateTime, nullable=False, index=True)

    # Incident details
    incident_type = Column(String(100))
    alarm_level = Column(Integer)
    status = Column(String(20), default="active")  # active, closed, etc.

    # Location
    address = Column(String(300))
    suburb = Column(String(100))
    map_reference = Column(String(50))
    latitude = Column(Float)
    longitude = Column(Float)
    geocode_attempted = Column(Boolean, default=False)
    geocode_success = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime)

    # CFS integration
    cfs_status = Column(String(50))
    cfs_last_update = Column(DateTime)

    agency = relationship("Agency", back_populates="incidents")
    messages = relationship("Message", back_populates="incident", order_by="Message.timestamp")
    units = relationship("IncidentUnit", back_populates="incident")

    __table_args__ = (
        Index('ix_incidents_date_agency', 'incident_date', 'agency_id'),
    )


class IncidentUnit(Base):
    """Units assigned to an incident"""
    __tablename__ = "incident_units"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    callsign = Column(String(20), nullable=False)
    dispatched_at = Column(DateTime)
    status = Column(String(20), default="dispatched")  # dispatched, responding, on_scene, etc.

    incident = relationship("Incident", back_populates="units")

    __table_args__ = (
        Index('ix_incident_units_incident_callsign', 'incident_id', 'callsign'),
    )


class Location(Base):
    """Geocoded locations cache"""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    address_hash = Column(String(64), unique=True, nullable=False, index=True)
    original_address = Column(String(300), nullable=False)
    normalized_address = Column(String(300))
    latitude = Column(Float)
    longitude = Column(Float)
    geocode_success = Column(Boolean, default=False)
    geocode_source = Column(String(50))  # nominatim, fuzzy_match, etc.
    created_at = Column(DateTime, default=datetime.utcnow)


class SAStreet(Base):
    """South Australian street names for fuzzy matching"""
    __tablename__ = "sa_streets"

    id = Column(Integer, primary_key=True, index=True)
    street_name = Column(String(100), nullable=False, index=True)
    suburb = Column(String(100), index=True)
    postcode = Column(String(10))
    full_address = Column(String(200))
