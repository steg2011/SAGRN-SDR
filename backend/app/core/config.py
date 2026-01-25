from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# Project root directory (parent of backend)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    app_name: str = "SAGRN SDR Monitor"
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR}/sagrn.db"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "sagrn-sdr-monitor/1.0"
    cfs_incidents_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_current_incidents.xml"
    cfs_cap_xml: str = "https://data.eso.sa.gov.au/prod/cfs/criimson/cfs_cap_incidents.xml"
    message_retention_days: int = 30
    geocode_rate_limit: float = 1.0  # 1 request per second

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
