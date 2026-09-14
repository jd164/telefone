import re
import asyncio
import logging
from bs4 import BeautifulSoup
from app.engine.scrapers.base import BaseScraper
from app.models.schemas import ScraperSourceResult, CrowdsourcedComment

logger = logging.getLogger(__name__)


class UnknownPhoneScraper(BaseScraper):
    source_name: str = "UnknownPhone / ListaSpam"

    async def query(self, e164: str, national_format: str) -> ScraperSourceResult:
        clean_num = re.sub(r"\D", "", e164)
        if clean_num.startswith("351"):
            nat = clean_num[3:]
            url = f"https://www.unknownphone.com/phone/{nat}"
        else:
            url = f"https://www.unknownphone.com/phone/{clean_num}"

        try:
            # Run curl_cffi in a thread executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            html = await loop.run_in_executor(None, self._fetch_curl, url)
            if not html:
                return ScraperSourceResult(
                    source_name=self.source_name,
                    success=False,
                    error_message="Sem resposta de UnknownPhone",
                )
            return self._parse_html(html)
        except Exception as exc:
            logger.debug("UnknownPhone scraper error: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=str(exc),
            )

    def _fetch_curl(self, url: str) -> str:
        try:
            from curl_cffi import requests as cffi_requests
            res = cffi_requests.get(url, impersonate="chrome120", timeout=5)
            if res.status_code == 200:
                return res.text
        except Exception as e:
            logger.debug("curl_cffi fetch failed: %s", e)
        return ""

    def _parse_html(self, html: str) -> ScraperSourceResult:
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = html.lower()

            # Check if there are no reports
            if "no one has left any comments yet" in text or "ainda não foram reportadas queixas" in text or "no reviews yet" in text:
                return ScraperSourceResult(
                    source_name=self.source_name,
                    success=True,
                    spam_score=0.0,
                    search_count=0,
                    report_count=0,
                    top_tags=[],
                    comments=[],
                )

            # Search count
            search_count = 0
            search_matches = re.findall(r"(\d+[\d\s,.]*)\s*(?:searches|queries|lookups)", text)
            if search_matches:
                search_count = int(re.sub(r"\D", "", search_matches[0]))

            # Reports count
            reports_count = 0
            rep_matches = re.findall(r"(\d+[\d\s,.]*)\s*(?:reports|complaints|reviews)", text)
            if rep_matches:
                reports_count = int(re.sub(r"\D", "", rep_matches[0]))

            # Calculate spam score based on reports
            spam_score = 0.0
            if reports_count > 10:
                spam_score = 8.5
            elif reports_count > 3:
                spam_score = 6.0
            elif reports_count > 0:
                spam_score = 4.0

            # Comments
            comments = []
            comment_boxes = soup.find_all(class_=re.compile(r"comment_text|user_comment|comment-body", re.I))
            for box in comment_boxes[:3]:
                txt = box.get_text(separator=" ", strip=True)
                if len(txt) > 10:
                    comments.append(
                        CrowdsourcedComment(
                            source=self.source_name,
                            author="Utilizador UnknownPhone",
                            text=txt[:280],
                        )
                    )

            return ScraperSourceResult(
                source_name=self.source_name,
                success=True,
                spam_score=spam_score,
                search_count=search_count,
                report_count=reports_count,
                top_tags=["Telemarketing"] if reports_count > 5 else [],
                comments=comments,
            )
        except Exception as exc:
            logger.debug("Error parsing UnknownPhone HTML: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=str(exc),
            )
