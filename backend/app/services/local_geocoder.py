"""
Local geocoding service for SA emergency incidents.

Uses locally imported SA road network (sa_roads) and G-NAF address data (sa_addresses)
to resolve pager message locations without external geocoding services.

Handles two address patterns:
1. Cross-street: "SOUTH RD / ANZAC HWY" or "HEASLIP RD/LOVEY RD PENFIELD"
2. Street address: "123 HORROCKS HWY" or "45 MAIN STREET ADELAIDE"

Uses RapidFuzz for fuzzy string matching and Shapely for geometry intersection.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional, Tuple, List

from rapidfuzz import fuzz, process
from shapely import wkt as shapely_wkt
from shapely.ops import nearest_points
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SARoad, SAAddress, Location, Incident
from app.services.suburb_matcher import get_suburb_matcher


# Street type abbreviation expansions (for normalizing pager messages)
STREET_TYPE_EXPAND = {
    'RD': 'ROAD', 'ST': 'STREET', 'AV': 'AVENUE', 'AVE': 'AVENUE',
    'DR': 'DRIVE', 'CT': 'COURT', 'PL': 'PLACE', 'CR': 'CRESCENT',
    'CRES': 'CRESCENT', 'TCE': 'TERRACE', 'TER': 'TERRACE',
    'HWY': 'HIGHWAY', 'BVD': 'BOULEVARD', 'BLVD': 'BOULEVARD',
    'CL': 'CLOSE', 'GR': 'GROVE', 'GRV': 'GROVE', 'LN': 'LANE',
    'WY': 'WAY', 'CIR': 'CIRCLE', 'PKY': 'PARKWAY', 'PKWY': 'PARKWAY',
    'PDE': 'PARADE', 'ESP': 'ESPLANADE', 'CCT': 'CIRCUIT',
}

# Reverse map: full name to abbreviation (for matching against DB which may use either form)
STREET_TYPE_ABBREV = {v: k for k, v in STREET_TYPE_EXPAND.items()}

# All known street types (both abbreviated and full)
ALL_STREET_TYPES = set(STREET_TYPE_EXPAND.keys()) | set(STREET_TYPE_EXPAND.values())

# Cross-street separators
CROSS_STREET_PATTERN = re.compile(
    r'^(.+?)\s*(?:/|&|\bAND\b|\bAND\s+|\s+AND\s+)\s*(.+)$',
    re.IGNORECASE
)

# Street address pattern: number at start
ADDRESS_PATTERN = re.compile(
    r'^(\d+[A-Z]?)\s+(.+)$'
)

# Map reference pattern to strip
MAP_REF_PATTERN = re.compile(r',?\s*MAP:?\s*[A-Z]*\s*\d+\s*[A-Z]?\s*\d*', re.IGNORECASE)

# Minimum fuzzy match score
MIN_FUZZY_SCORE = 75
MIN_CROSS_STREET_SCORE = 70


@dataclass
class ParsedAddress:
    """Parsed address components from a pager message."""
    address_type: str  # 'cross_street', 'street_address', 'suburb_only'
    street_number: Optional[str] = None
    road_a: Optional[str] = None
    road_b: Optional[str] = None
    street_name: Optional[str] = None
    street_type: Optional[str] = None
    suburb: Optional[str] = None
    raw: str = ''


@dataclass
class GeoResult:
    """Geocoding result."""
    latitude: float
    longitude: float
    confidence: float  # 0-100
    source: str  # LOCAL_LOOKUP
    matched_address: str  # What we matched against


class LocalGeocoder:
    """Local geocoding engine using SA road and address data."""

    def __init__(self):
        self.suburb_matcher = get_suburb_matcher()
        self._road_name_cache = {}  # suburb -> [road_names]

    def parse_address(self, address: str, suburb: Optional[str] = None) -> ParsedAddress:
        """Parse a pager message address into components."""
        if not address:
            return ParsedAddress(address_type='suburb_only', suburb=suburb, raw=address or '')

        raw = address
        address = address.strip().upper()

        # Remove map reference
        address = MAP_REF_PATTERN.sub('', address).strip()

        # Remove facility prefix (@FACILITY_NAME)
        address = re.sub(r'^@[^,]+,?\s*', '', address).strip()

        # Try to extract suburb from the address if not provided
        if not suburb:
            suburb = self._extract_suburb(address)

        # Remove suburb from address for further parsing
        address_without_suburb = address
        if suburb:
            suburb = suburb.strip().upper()
            # Remove suburb from end of address
            pattern = re.compile(r',?\s*' + re.escape(suburb) + r'\s*$', re.IGNORECASE)
            address_without_suburb = pattern.sub('', address).strip()
            # Also try removing from start (CFS JSON format: "SUBURB, STREET")
            pattern2 = re.compile(r'^' + re.escape(suburb) + r',?\s*', re.IGNORECASE)
            if address_without_suburb == address:
                address_without_suburb = pattern2.sub('', address).strip()

        # Remove trailing commas
        address_without_suburb = address_without_suburb.strip().rstrip(',').strip()

        if not address_without_suburb:
            return ParsedAddress(address_type='suburb_only', suburb=suburb, raw=raw)

        # Check for cross-street pattern
        cross_match = CROSS_STREET_PATTERN.match(address_without_suburb)
        if cross_match:
            road_a = self._normalize_road_name(cross_match.group(1).strip())
            road_b = self._normalize_road_name(cross_match.group(2).strip())
            return ParsedAddress(
                address_type='cross_street',
                road_a=road_a,
                road_b=road_b,
                suburb=suburb,
                raw=raw
            )

        # Check for street address pattern (number + street)
        addr_match = ADDRESS_PATTERN.match(address_without_suburb)
        if addr_match:
            number = addr_match.group(1)
            street_part = addr_match.group(2).strip()
            name, stype = self._split_street_name_type(street_part)
            return ParsedAddress(
                address_type='street_address',
                street_number=number,
                street_name=name,
                street_type=stype,
                suburb=suburb,
                raw=raw
            )

        # Treat as a street name without number
        name, stype = self._split_street_name_type(address_without_suburb)
        return ParsedAddress(
            address_type='street_address',
            street_name=name,
            street_type=stype,
            suburb=suburb,
            raw=raw
        )

    def _extract_suburb(self, address: str) -> Optional[str]:
        """Try to extract a suburb from the address text."""
        result = self.suburb_matcher.extract_suburb_from_text(address)
        if result:
            return result
        return None

    def _normalize_road_name(self, name: str) -> str:
        """Normalize a road name by expanding abbreviations."""
        parts = name.upper().split()
        normalized = []
        for part in parts:
            if part in STREET_TYPE_EXPAND:
                normalized.append(STREET_TYPE_EXPAND[part])
            else:
                normalized.append(part)
        return ' '.join(normalized)

    def _split_street_name_type(self, street: str) -> Tuple[str, Optional[str]]:
        """Split 'MAIN ROAD' into ('MAIN', 'ROAD')."""
        parts = street.upper().split()
        if not parts:
            return (street.upper(), None)

        # Check last word for street type
        last = parts[-1]
        if last in ALL_STREET_TYPES:
            name = ' '.join(parts[:-1])
            stype = STREET_TYPE_EXPAND.get(last, last)
            return (name, stype) if name else (street.upper(), None)

        return (' '.join(parts), None)

    async def geocode_incident(self, db: AsyncSession, incident: Incident) -> bool:
        """
        Geocode an incident using local data.
        Returns True if successful.
        """
        if incident.geocode_attempted and incident.location_source == 'OFFICIAL_FEED':
            return incident.geocode_success

        address = incident.address
        suburb = incident.suburb

        if not address and not suburb:
            incident.geocode_attempted = True
            await db.commit()
            return False

        # Check cache first
        cache_key = f"{address or ''}|{suburb or ''}"
        address_hash = hashlib.sha256(cache_key.upper().encode()).hexdigest()

        result = await db.execute(
            select(Location).where(Location.address_hash == address_hash)
        )
        cached = result.scalar_one_or_none()

        if cached:
            incident.latitude = cached.latitude
            incident.longitude = cached.longitude
            incident.geocode_success = cached.geocode_success
            incident.geocode_attempted = True
            incident.location_source = cached.geocode_source
            incident.location_confidence = 100.0 if cached.geocode_success else 0.0
            await db.commit()
            return cached.geocode_success

        # Parse the address
        parsed = self.parse_address(address, suburb)

        # Try to geocode
        geo_result = None

        if parsed.address_type == 'cross_street':
            geo_result = await self._resolve_cross_street(db, parsed)

        elif parsed.address_type == 'street_address':
            geo_result = await self._resolve_street_address(db, parsed)

        if not geo_result and parsed.suburb:
            # Fallback: suburb centroid (very rough)
            geo_result = await self._resolve_suburb_centroid(db, parsed.suburb)

        # Update incident
        incident.geocode_attempted = True
        if geo_result:
            incident.latitude = geo_result.latitude
            incident.longitude = geo_result.longitude
            incident.geocode_success = True
            incident.location_source = geo_result.source
            incident.location_confidence = geo_result.confidence

            # Cache the result
            location = Location(
                address_hash=address_hash,
                original_address=cache_key,
                normalized_address=geo_result.matched_address,
                latitude=geo_result.latitude,
                longitude=geo_result.longitude,
                geocode_success=True,
                geocode_source='LOCAL_LOOKUP'
            )
            db.add(location)
        else:
            incident.geocode_success = False
            incident.location_source = 'LOCAL_LOOKUP'
            incident.location_confidence = 0.0

            # Cache the failure
            location = Location(
                address_hash=address_hash,
                original_address=cache_key,
                geocode_success=False,
                geocode_source='LOCAL_LOOKUP'
            )
            db.add(location)

        await db.commit()
        return incident.geocode_success

    async def _resolve_cross_street(
        self, db: AsyncSession, parsed: ParsedAddress
    ) -> Optional[GeoResult]:
        """Resolve a cross-street reference to coordinates."""
        if not parsed.road_a or not parsed.road_b:
            return None

        # Find both roads in the database
        road_a_rows = await self._find_road(db, parsed.road_a, parsed.suburb)
        road_b_rows = await self._find_road(db, parsed.road_b, parsed.suburb)

        if not road_a_rows or not road_b_rows:
            # Try without suburb constraint (roads may cross suburb boundaries)
            if not road_a_rows:
                road_a_rows = await self._find_road(db, parsed.road_a, None)
            if not road_b_rows:
                road_b_rows = await self._find_road(db, parsed.road_b, None)

        if not road_a_rows or not road_b_rows:
            return None

        # Try to find intersection using Shapely
        best_result = None
        best_distance = float('inf')

        for road_a in road_a_rows:
            if not road_a.geometry_wkt:
                continue
            try:
                geom_a = shapely_wkt.loads(road_a.geometry_wkt)
            except Exception:
                continue

            for road_b in road_b_rows:
                if not road_b.geometry_wkt:
                    continue
                try:
                    geom_b = shapely_wkt.loads(road_b.geometry_wkt)
                except Exception:
                    continue

                # Check for actual intersection
                if geom_a.intersects(geom_b):
                    intersection = geom_a.intersection(geom_b)
                    if not intersection.is_empty:
                        # Get the centroid of the intersection
                        pt = intersection.centroid
                        return GeoResult(
                            latitude=pt.y,
                            longitude=pt.x,
                            confidence=95.0,
                            source='LOCAL_LOOKUP',
                            matched_address=f"{road_a.road_name} / {road_b.road_name}"
                        )

                # Find nearest points between the two geometries
                p1, p2 = nearest_points(geom_a, geom_b)
                dist = p1.distance(p2)

                # If they're close enough (within ~500m at SA latitudes, ~0.005 degrees)
                if dist < 0.005 and dist < best_distance:
                    best_distance = dist
                    mid_x = (p1.x + p2.x) / 2
                    mid_y = (p1.y + p2.y) / 2
                    # Lower confidence the further apart they are
                    conf = max(60.0, 90.0 - (dist * 5000))
                    best_result = GeoResult(
                        latitude=mid_y,
                        longitude=mid_x,
                        confidence=conf,
                        source='LOCAL_LOOKUP',
                        matched_address=f"{road_a.road_name} / {road_b.road_name}"
                    )

        return best_result

    async def _resolve_street_address(
        self, db: AsyncSession, parsed: ParsedAddress
    ) -> Optional[GeoResult]:
        """Resolve a street address to coordinates using G-NAF data."""
        if not parsed.street_name:
            return None

        # Expand abbreviations in the street name for matching
        search_name = parsed.street_name
        search_type = parsed.street_type

        # First try G-NAF address lookup (exact number + fuzzy street)
        if parsed.street_number:
            result = await self._find_gnaf_address(
                db, parsed.street_number, search_name, search_type, parsed.suburb
            )
            if result:
                return result

        # Fallback: road network centroid
        roads = await self._find_road(
            db, f"{search_name} {search_type}" if search_type else search_name,
            parsed.suburb
        )
        if roads:
            road = roads[0]
            return GeoResult(
                latitude=road.centroid_lat,
                longitude=road.centroid_lon,
                confidence=60.0,
                source='LOCAL_LOOKUP',
                matched_address=f"{road.road_name} {road.road_type or ''} {road.suburb or ''}".strip()
            )

        return None

    async def _resolve_suburb_centroid(
        self, db: AsyncSession, suburb: str
    ) -> Optional[GeoResult]:
        """Get approximate centroid of a suburb from address data."""
        result = await db.execute(
            select(
                func.avg(SAAddress.latitude).label('lat'),
                func.avg(SAAddress.longitude).label('lon'),
                func.count().label('cnt')
            ).where(SAAddress.suburb == suburb.upper())
        )
        row = result.first()
        if row and row.cnt > 0:
            return GeoResult(
                latitude=row.lat,
                longitude=row.lon,
                confidence=30.0,
                source='LOCAL_LOOKUP',
                matched_address=f"SUBURB: {suburb}"
            )

        # Try road centroids
        result = await db.execute(
            select(
                func.avg(SARoad.centroid_lat).label('lat'),
                func.avg(SARoad.centroid_lon).label('lon'),
                func.count().label('cnt')
            ).where(SARoad.suburb == suburb.upper())
        )
        row = result.first()
        if row and row.cnt > 0:
            return GeoResult(
                latitude=row.lat,
                longitude=row.lon,
                confidence=20.0,
                source='LOCAL_LOOKUP',
                matched_address=f"SUBURB: {suburb}"
            )

        return None

    async def _find_road(
        self, db: AsyncSession, road_name: str, suburb: Optional[str],
        limit: int = 10
    ) -> List[SARoad]:
        """Find road segments by name with fuzzy matching."""
        road_name = road_name.upper().strip()

        # Split off street type if present
        name_part, type_part = self._split_street_name_type(road_name)

        # Try exact match first
        query = select(SARoad)
        conditions = [SARoad.road_name == name_part]
        if suburb:
            conditions.append(SARoad.suburb == suburb.upper())
        if type_part:
            conditions.append(SARoad.road_type == type_part)

        result = await db.execute(query.where(and_(*conditions)).limit(limit))
        roads = result.scalars().all()
        if roads:
            return list(roads)

        # Try without type constraint
        conditions = [SARoad.road_name == name_part]
        if suburb:
            conditions.append(SARoad.suburb == suburb.upper())
        result = await db.execute(query.where(and_(*conditions)).limit(limit))
        roads = result.scalars().all()
        if roads:
            return list(roads)

        # Try LIKE match (handles partial names)
        conditions = [SARoad.road_name.like(f"%{name_part}%")]
        if suburb:
            conditions.append(SARoad.suburb == suburb.upper())
        result = await db.execute(query.where(and_(*conditions)).limit(50))
        candidates = result.scalars().all()

        if candidates:
            # Fuzzy rank
            scored = []
            for road in candidates:
                score = fuzz.token_sort_ratio(name_part, road.road_name)
                if score >= MIN_CROSS_STREET_SCORE:
                    scored.append((score, road))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [r for _, r in scored[:limit]]

        # Last resort: search all roads in suburb with fuzzy matching
        if suburb:
            result = await db.execute(
                select(SARoad).where(SARoad.suburb == suburb.upper())
            )
            all_roads = result.scalars().all()
            if all_roads:
                road_names = {r.road_name for r in all_roads}
                matches = process.extract(
                    name_part, list(road_names),
                    scorer=fuzz.token_sort_ratio,
                    limit=3,
                    score_cutoff=MIN_CROSS_STREET_SCORE
                )
                if matches:
                    best_name = matches[0][0]
                    return [r for r in all_roads if r.road_name == best_name][:limit]

        return []

    async def _find_gnaf_address(
        self, db: AsyncSession,
        street_number: str, street_name: str,
        street_type: Optional[str], suburb: Optional[str]
    ) -> Optional[GeoResult]:
        """Find an address in the G-NAF data."""
        # Try exact match
        conditions = [
            SAAddress.street_number == street_number,
            SAAddress.street_name == street_name.upper(),
        ]
        if suburb:
            conditions.append(SAAddress.suburb == suburb.upper())
        if street_type:
            conditions.append(SAAddress.street_type == street_type.upper())

        result = await db.execute(
            select(SAAddress).where(and_(*conditions)).limit(1)
        )
        addr = result.scalar_one_or_none()
        if addr:
            return GeoResult(
                latitude=addr.latitude,
                longitude=addr.longitude,
                confidence=95.0,
                source='LOCAL_LOOKUP',
                matched_address=f"{addr.street_number} {addr.street_name} {addr.street_type or ''} {addr.suburb or ''}".strip()
            )

        # Try fuzzy street name match
        conditions = [SAAddress.street_number == street_number]
        if suburb:
            conditions.append(SAAddress.suburb == suburb.upper())

        # Get candidate street names in the suburb
        result = await db.execute(
            select(SAAddress.street_name).distinct()
            .where(and_(*conditions))
        )
        candidates = [row[0] for row in result.all()]

        if candidates:
            matches = process.extract(
                street_name.upper(), candidates,
                scorer=fuzz.token_sort_ratio,
                limit=1,
                score_cutoff=MIN_FUZZY_SCORE
            )
            if matches:
                matched_name = matches[0][0]
                match_score = matches[0][1]

                conditions = [
                    SAAddress.street_number == street_number,
                    SAAddress.street_name == matched_name,
                ]
                if suburb:
                    conditions.append(SAAddress.suburb == suburb.upper())

                result = await db.execute(
                    select(SAAddress).where(and_(*conditions)).limit(1)
                )
                addr = result.scalar_one_or_none()
                if addr:
                    return GeoResult(
                        latitude=addr.latitude,
                        longitude=addr.longitude,
                        confidence=match_score,
                        source='LOCAL_LOOKUP',
                        matched_address=f"{addr.street_number} {addr.street_name} {addr.street_type or ''} {addr.suburb or ''}".strip()
                    )

        return None


# Singleton
_local_geocoder = None

def get_local_geocoder() -> LocalGeocoder:
    global _local_geocoder
    if _local_geocoder is None:
        _local_geocoder = LocalGeocoder()
    return _local_geocoder
