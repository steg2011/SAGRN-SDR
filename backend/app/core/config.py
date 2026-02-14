from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# Project root directory (parent of backend)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "SAGRN SDR Monitor"
    database_url: str = "postgresql+asyncpg://sagrn:sagrn@db:5432/sagrn"
    redis_url: str = "redis://redis:6379/0"

    # CFS incident feeds (provides location data and official coordinates)
    cfs_incidents_json: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.json"
    cfs_incidents_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml"
    cfs_cap_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml"

    # Mapbox token (served to frontend via /api/config)
    mapbox_token: str = ""

    # Data retention - 365 days (32GB RAM, 240GB SSD with PostgreSQL)
    message_retention_hours: int = 8760

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # Frontend static files directory (built React app)
    static_dir: str = str(PROJECT_ROOT / "frontend" / "build")

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
