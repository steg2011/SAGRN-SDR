from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
import os

# Project root directory (parent of backend)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    app_name: str = "SAGRN SDR Monitor"
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR}/sagrn.db"

    # CFS incident feeds (provides location data, replacing Nominatim geocoding)
    cfs_incidents_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml"
    cfs_cap_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml"

    # Data retention - 24 hours for lightweight operation
    message_retention_hours: int = 24

    # Server configuration for GCP free tier
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1  # Single worker for free tier memory constraints

    # Frontend static files directory (built React app)
    static_dir: str = str(PROJECT_ROOT / "frontend" / "build")

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
