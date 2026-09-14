import random
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import httpx
from app.models.schemas import ScraperSourceResult
from app.core.config import settings

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    """
    Base class for phone reputation scrapers and external intelligence workers.
    Ensures safe, asynchronous requests with spoofed headers and exception isolation.
    """

    source_name: str = "BaseScraper"

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    async def fetch_html(self, url: str, timeout: Optional[float] = None) -> Optional[str]:
        timeout_val = timeout or settings.SCRAPER_TIMEOUT_SECONDS
        try:
            async with httpx.AsyncClient(
                headers=self.get_headers(),
                timeout=timeout_val,
                follow_redirects=True,
                verify=False  # Avoid SSL renegotiation/cert failures on some scrape targets
            ) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 404:
                    logger.debug("[%s] Page not found (404) for %s", self.source_name, url)
                    return None
                elif response.status_code == 429:
                    logger.warning("[%s] Rate limited (429) for %s", self.source_name, url)
                    return None
                else:
                    logger.debug("[%s] Received HTTP status %d for %s", self.source_name, response.status_code, url)
                    return None
        except httpx.TimeoutException:
            logger.debug("[%s] Request timed out for %s", self.source_name, url)
            return None
        except Exception as exc:
            logger.debug("[%s] Network exception fetching %s: %s", self.source_name, url, exc)
            return None

    @abstractmethod
    async def query(self, e164: str, national_format: str) -> ScraperSourceResult:
        """Execute the scrape/API lookup and return standardized ScraperSourceResult."""
        pass
