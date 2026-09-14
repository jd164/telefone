from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Phone Number Intelligence Aggregator"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    ANACOM_DATA_FILE: Path = DATA_DIR / "anacom_pnn_pt.json"
    SQLITE_DB_PATH: Path = DATA_DIR / "phone_intel.db"

    # Cache Settings
    CACHE_ENABLED: bool = True
    CACHE_TTL_HOURS: int = 24  # 24-hour TTL for scraping & external APIs

    # External APIs (Optional - fallbacks to resilient scrapers if empty)
    TELLOWS_API_KEY: str = ""
    TELLOWS_PARTNER_NAME: str = ""
    GOOGLE_PLACES_API_KEY: str = ""

    # Request timeouts & scraper options
    SCRAPER_TIMEOUT_SECONDS: float = 6.0
    SCRAPER_CONCURRENCY_LIMIT: int = 5
    DEFAULT_COUNTRY: str = "PT"

    # Risk Scoring Weights (0.0 to 1.0)
    WEIGHT_VOIP: float = 0.15
    WEIGHT_COMMUNITY_SCORE: float = 0.40
    WEIGHT_REPORT_VOLUME: float = 0.25
    WEIGHT_VERIFIED_BUSINESS: float = 0.20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
