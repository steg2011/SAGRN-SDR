import asyncio
import hashlib
import re
from typing import Optional, Tuple
from datetime import datetime
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import Location, Incident
from app.services.suburb_matcher import get_suburb_matcher


settings = get_settings()


class GeocoderService:
    """Geocoding service using Nominatim with fuzzy matching for SA addresses"""

    def __init__(self):
        self.rate_limiter = asyncio.Semaphore(1)
        self.last_request_time = 0
        self.min_interval = settings.geocode_rate_limit
        self.suburb_matcher = get_suburb_matcher()

    # Street type expansions
    STREET_TYPES = {
        'RD': 'ROAD',
        'ST': 'STREET',
        'AV': 'AVENUE',
        'AVE': 'AVENUE',
        'DR': 'DRIVE',
        'CT': 'COURT',
        'PL': 'PLACE',
        'CR': 'CRESCENT',
        'CRES': 'CRESCENT',
        'TCE': 'TERRACE',
        'HWY': 'HIGHWAY',
        'BVD': 'BOULEVARD',
        'BLVD': 'BOULEVARD',
    }

    async def geocode_incident(
        self,
        db: AsyncSession,
        incident: Incident
    ) -> bool:
        """
        Geocode an incident address. Returns True if successful.
        Only attempts geocoding once per incident.
        """
        if incident.geocode_attempted:
            return incident.geocode_success

        # Mark as attempted immediately to prevent duplicate attempts
        incident.geocode_attempted = True
        await db.commit()

        if not incident.address:
            return False

        # Check cache first
        address_hash = self._hash_address(incident.address)
        cached = await self._get_cached_location(db, address_hash)

        if cached:
            incident.latitude = cached.latitude
            incident.longitude = cached.longitude
            incident.geocode_success = cached.geocode_success
            await db.commit()
            return cached.geocode_success

        # Normalize address for geocoding
        normalized = self._normalize_address(incident.address, incident.suburb)

        if not normalized:
            await self._cache_location(db, address_hash, incident.address, None, None, False)
            return False

        # Geocode with Nominatim
        coords = await self._geocode_nominatim(normalized)

        if coords:
            incident.latitude = coords[0]
            incident.longitude = coords[1]
            incident.geocode_success = True
            await self._cache_location(db, address_hash, incident.address, coords[0], coords[1], True)
        else:
            await self._cache_location(db, address_hash, incident.address, None, None, False)

        await db.commit()
        return incident.geocode_success

    def _hash_address(self, address: str) -> str:
        """Create a hash of the address for caching"""
        normalized = address.upper().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _get_cached_location(
        self,
        db: AsyncSession,
        address_hash: str
    ) -> Optional[Location]:
        """Get cached location by address hash"""
        result = await db.execute(
            select(Location).where(Location.address_hash == address_hash)
        )
        return result.scalar_one_or_none()

    async def _cache_location(
        self,
        db: AsyncSession,
        address_hash: str,
        original_address: str,
        latitude: Optional[float],
        longitude: Optional[float],
        success: bool
    ):
        """Cache geocoding result"""
        location = Location(
            address_hash=address_hash,
            original_address=original_address,
            latitude=latitude,
            longitude=longitude,
            geocode_success=success,
            geocode_source='nominatim' if success else 'failed'
        )
        db.add(location)
        await db.commit()

    def _normalize_address(
        self,
        address: str,
        suburb: Optional[str] = None
    ) -> Optional[str]:
        """Normalize and clean address for geocoding using fuzzy suburb matching"""
        if not address:
            return None

        # Remove facility prefixes
        address = re.sub(r'^@[^@]+', '', address).strip()

        # Remove map references
        address = re.sub(r'MAP:[A-Z]+\s+\d+[A-Z]?\s+[A-Z0-9]+', '', address)
        address = re.sub(r'\d{1,3}\s+[A-Z]\s+\d{1,2}', '', address)

        # Normalize suburb using fuzzy matching if provided
        if suburb:
            normalized_suburb = self.suburb_matcher.normalize(suburb)
            if normalized_suburb != suburb.upper():
                # Replace the original suburb with the corrected one
                address = address.replace(suburb, normalized_suburb)
                address = address.replace(suburb.upper(), normalized_suburb)

        # Try to find and normalize any suburb-like words in the address
        # Split address and check each word/phrase against suburb list
        words = address.upper().split()
        normalized_words = []
        i = 0
        while i < len(words):
            # Try multi-word suburb matches (up to 3 words)
            matched = False
            for length in range(3, 0, -1):
                if i + length <= len(words):
                    phrase = ' '.join(words[i:i+length])
                    match_result = self.suburb_matcher.match(phrase)
                    if match_result and match_result[1] >= 85:  # High confidence for in-address matching
                        normalized_words.append(match_result[0])
                        i += length
                        matched = True
                        break

            if not matched:
                # Check if it's a street type abbreviation
                if words[i] in self.STREET_TYPES:
                    normalized_words.append(self.STREET_TYPES[words[i]])
                else:
                    normalized_words.append(words[i])
                i += 1

        address = ' '.join(normalized_words)

        # Add South Australia if not present
        if 'SA' not in address.upper() and 'SOUTH AUSTRALIA' not in address.upper():
            address = f"{address}, South Australia, Australia"

        return address.strip()

    async def _geocode_nominatim(
        self,
        address: str
    ) -> Optional[Tuple[float, float]]:
        """Query Nominatim geocoder with rate limiting"""
        async with self.rate_limiter:
            # Enforce rate limit
            now = asyncio.get_event_loop().time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)

            self.last_request_time = asyncio.get_event_loop().time()

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{settings.nominatim_url}/search",
                        params={
                            'q': address,
                            'format': 'json',
                            'limit': 1,
                            'countrycodes': 'au',
                            'addressdetails': 1
                        },
                        headers={
                            'User-Agent': settings.nominatim_user_agent
                        }
                    )

                    if response.status_code == 200:
                        results = response.json()
                        if results:
                            lat = float(results[0]['lat'])
                            lon = float(results[0]['lon'])
                            return (lat, lon)

            except Exception as e:
                print(f"Geocoding error for {address}: {e}")

            return None


class BackgroundGeocoder:
    """Background geocoding processor for pending addresses"""

    def __init__(self, geocoder: GeocoderService):
        self.geocoder = geocoder
        self.running = False

    async def process_pending(self, db: AsyncSession):
        """Process pending geocoding requests - new jobs first, then old"""
        self.running = True

        while self.running:
            # Get newest incident without geocoding attempted
            result = await db.execute(
                select(Incident)
                .where(Incident.geocode_attempted == False)
                .where(Incident.address.isnot(None))
                .order_by(Incident.created_at.desc())
                .limit(1)
            )
            incident = result.scalar_one_or_none()

            if incident:
                await self.geocoder.geocode_incident(db, incident)
            else:
                # No pending incidents, wait before checking again
                await asyncio.sleep(5)

            # Rate limit: 1 per second
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
