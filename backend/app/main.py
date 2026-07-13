import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models.database import init_db, async_session
from app.api.routes import router
from app.services.incident_service import IncidentService
from app.services.cfs_integration import CFSIntegrationService
from app.services.waze_service import get_waze_service
from app.services.event_manager import get_event_manager
from app.core.config import get_settings

settings = get_settings()
scheduler = AsyncIOScheduler()

# Services
incident_service = IncidentService()
cfs_service = CFSIntegrationService()
waze_service = get_waze_service()


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
        await incident_service.cleanup_old_messages(db, hours=settings.message_retention_hours)
    print(f"Cleaned up messages older than {settings.message_retention_hours} hours")


async def fetch_cfs_incidents():
    """Scheduled task to fetch CFS incident updates (provides location data)"""
    async with async_session() as db:
        await cfs_service.update_incidents(db)
    print("CFS incidents updated")


async def fetch_waze_incidents():
    """Scheduled task to fetch Waze traffic incidents (every 2 minutes)"""
    async with async_session() as db:
        new_count = await waze_service.process_alerts(db)
        if new_count > 0:
            print(f"Waze: {new_count} new traffic incidents")
        # Also cleanup stale incidents
        await waze_service.cleanup_old_alerts(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    await startup_tasks()

    # Schedule periodic tasks (optimized for lightweight operation)
    scheduler.add_job(cleanup_old_data, 'interval', hours=1)  # More frequent cleanup for 24hr retention
    scheduler.add_job(fetch_cfs_incidents, 'interval', minutes=5)
    scheduler.add_job(fetch_waze_incidents, 'interval', minutes=2)  # Waze updates every 2 minutes
    scheduler.start()

    # Run initial Waze fetch. Never let a bad feed or a transient DB error block
    # startup -- the scheduler retries every 2 minutes anyway.
    try:
        await fetch_waze_incidents()
    except Exception as e:
        print(f"Initial Waze fetch failed, continuing startup: {e}")

    print("SAGRN SDR Monitor started (Lightweight GCP Edition)")

    yield

    # Shutdown
    scheduler.shutdown()
    await get_event_manager().close()
    print("SAGRN SDR Monitor stopped")


# Create FastAPI app
app = FastAPI(
    title="SAGRN SDR Monitor",
    description="Emergency services pager monitoring system for South Australia (Lightweight)",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend (needed for development, static serving handles production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve static frontend files if build directory exists
static_path = Path(settings.static_dir)
if static_path.exists() and static_path.is_dir():
    # Mount static files (CSS, JS, etc.)
    app.mount("/static", StaticFiles(directory=str(static_path / "static")), name="static")

    # Serve index.html for all non-API routes (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API calls
        if full_path.startswith("api/"):
            return None

        # Check if it's a file that exists
        file_path = static_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))

        # Otherwise serve index.html for SPA routing
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))

        return {"error": "Frontend not built. Run: cd frontend && npm run build"}


# Root endpoint (fallback if no static files)
@app.get("/")
async def root():
    # Check if frontend is built
    index_path = static_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    return {
        "name": "SAGRN SDR Monitor (Lightweight)",
        "status": "running",
        "message": "Frontend not built. Run: cd frontend && npm run build",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        workers=settings.workers
    )
