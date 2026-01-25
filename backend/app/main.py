import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.database import init_db, async_session
from app.api.routes import router
from app.services.incident_service import IncidentService
from app.services.geocoder import GeocoderService, BackgroundGeocoder
from app.services.cfs_integration import CFSIntegrationService
from app.core.config import get_settings

settings = get_settings()
scheduler = AsyncIOScheduler()

# Services
incident_service = IncidentService()
geocoder_service = GeocoderService()
cfs_service = CFSIntegrationService()


async def startup_tasks():
    """Run startup tasks"""
    # Initialize database
    await init_db()

    # Ensure agencies exist
    async with async_session() as db:
        await incident_service.ensure_agencies(db)

    print("Database initialized")


async def cleanup_old_data():
    """Scheduled task to clean up old data"""
    async with async_session() as db:
        await incident_service.cleanup_old_messages(db, days=settings.message_retention_days)
    print(f"Cleaned up messages older than {settings.message_retention_days} days")


async def fetch_cfs_incidents():
    """Scheduled task to fetch CFS incident updates"""
    async with async_session() as db:
        await cfs_service.update_incidents(db)
    print("CFS incidents updated")


async def geocode_pending():
    """Scheduled task to geocode pending addresses"""
    async with async_session() as db:
        from sqlalchemy import select
        from app.models.models import Incident

        # Get one pending incident
        result = await db.execute(
            select(Incident)
            .where(Incident.geocode_attempted == False)
            .where(Incident.address.isnot(None))
            .order_by(Incident.created_at.desc())
            .limit(1)
        )
        incident = result.scalar_one_or_none()

        if incident:
            await geocoder_service.geocode_incident(db, incident)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    await startup_tasks()

    # Schedule periodic tasks
    scheduler.add_job(cleanup_old_data, 'interval', hours=6)
    scheduler.add_job(fetch_cfs_incidents, 'interval', minutes=5)
    scheduler.add_job(geocode_pending, 'interval', seconds=2)  # 1 per 2 seconds for rate limit
    scheduler.start()

    print("SAGRN SDR Monitor started")

    yield

    # Shutdown
    scheduler.shutdown()
    print("SAGRN SDR Monitor stopped")


# Create FastAPI app
app = FastAPI(
    title="SAGRN SDR Monitor",
    description="Emergency services pager monitoring system for South Australia",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")


# Root endpoint
@app.get("/")
async def root():
    return {
        "name": "SAGRN SDR Monitor",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
