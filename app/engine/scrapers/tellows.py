import re
import logging
from bs4 import BeautifulSoup
from app.engine.scrapers.base import BaseScraper
from app.models.schemas import ScraperSourceResult, CrowdsourcedComment
from app.core.config import settings

logger = logging.getLogger(__name__)


class TellowsScraper(BaseScraper):
    source_name: str = "Tellows (Portugal & Global)"

    async def query(self, e164: str, national_format: str) -> ScraperSourceResult:
        clean_num = re.sub(r"\D", "", e164)
        if clean_num.startswith("351"):
            clean_national = clean_num[3:]
            url = f"https://www.tellows.pt/num/{clean_national}"
        else:
            url = f"https://www.tellows.com/num/{clean_num}"

        # If API key configured, prefer official API
        if settings.TELLOWS_API_KEY:
            return await self._query_api(clean_num)

        # Fallback to HTML scraping
        html = await self.fetch_html(url)
        if not html:
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message="Sem resposta de Tellows",
            )

        return self._parse_html(html)

    async def _query_api(self, clean_num: str) -> ScraperSourceResult:
        api_url = f"https://www.tellows.pt/basic/partner/num/{clean_num}?json=1&apikey={settings.TELLOWS_API_KEY}"
        html = await self.fetch_html(api_url)
        if not html:
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message="Tellows API request failed",
            )
        try:
            import json
            data = json.loads(html)
            raw_score = int(data.get("score", 5))
            searches = int(data.get("searches", 0))
            comments_data = data.get("comments", [])

            # Neutral 5 with no comments/searches is unrated clean
            if raw_score == 5 and len(comments_data) == 0 and searches == 0:
                spam_score = 0.0
            elif raw_score <= 4:
                spam_score = max(0.0, (raw_score - 1) * 0.5)  # 0 to 1.5 (Safe)
            else:
                spam_score = min(10.0, (raw_score - 5) * 2.5)  # 6 -> 2.5, 7 -> 5.0, 8 -> 7.5, 9 -> 10.0

            comments = [
                CrowdsourcedComment(
                    source=self.source_name,
                    author=c.get("author", "Anónimo"),
                    date=c.get("date"),
                    text=c.get("comment", ""),
                    tag=c.get("callertype"),
                )
                for c in comments_data[:3]
            ]
            return ScraperSourceResult(
                source_name=self.source_name,
                success=True,
                spam_score=round(spam_score, 1),
                search_count=searches,
                report_count=len(comments_data),
                top_tags=[data.get("callertype")] if data.get("callertype") else [],
                comments=comments,
            )
        except Exception as exc:
            logger.debug("Error parsing Tellows API response: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=f"JSON parse error: {exc}",
            )

    def _parse_html(self, html: str) -> ScraperSourceResult:
        try:
            soup = BeautifulSoup(html, "html.parser")
            title_text = soup.title.string if soup.title else ""

            # 1. Extract Score (Tellows 1-9 scale)
            # Default is 5 (neutral/unrated)
            raw_score = 5
            score_match = re.search(r"score\s*(?:do\s*n[úu]mero)?[:\s]+(\d+)", title_text, re.IGNORECASE)
            if score_match:
                raw_score = int(score_match.group(1))
            else:
                score_elem = soup.find(id="tellowsscore") or soup.find(class_=re.compile(r"score", re.I))
                if score_elem:
                    digits = re.findall(r"\d+", score_elem.get_text())
                    if digits:
                        raw_score = int(digits[0])

            raw_score = max(1, min(9, raw_score))

            # 2. Extract search count
            search_count = 0
            searches_match = re.search(r"(\d+[\d\s.,]*)\s*(?:pesquisas|pedidos|visualiza[çc][õo]es)", html, re.I)
            if searches_match:
                num_str = re.sub(r"\D", "", searches_match.group(1))
                if num_str:
                    search_count = int(num_str)

            # 3. Extract Real User Comments
            comments = []
            comment_nodes = soup.find_all(class_=re.compile(r"single[-_]?comment|reviewBody", re.I))
            for node in comment_nodes[:3]:
                text = node.get_text(separator=" ", strip=True)
                if text and len(text) > 10 and "tellows" not in text.lower():
                    comments.append(
                        CrowdsourcedComment(
                            source=self.source_name,
                            author="Utilizador Tellows",
                            text=text[:300],
                        )
                    )

            # 4. Tags: Only extract if score > 5 or from specific callertype element
            tags = []
            caller_type_elem = soup.find(id="callertype") or soup.find(class_=re.compile(r"callertype", re.I))
            if caller_type_elem:
                ct_text = caller_type_elem.get_text(strip=True)
                if ct_text and len(ct_text) < 30 and "desconhecido" not in ct_text.lower():
                    tags.append(ct_text)

            # Convert Tellows score to spam score:
            # Score 1-4: Trusted / Safe (0.0 to 1.5)
            # Score 5 with 0 comments: Unrated / Clean (0.0)
            # Score 5 with comments/searches: Neutral (2.0)
            # Score 6: Suspect (3.5)
            # Score 7: Annoying / Telemarketing (6.0)
            # Score 8: Dangerous (8.0)
            # Score 9: Severe Fraud / Robocalls (10.0)
            if raw_score == 5:
                if len(comments) == 0 and search_count <= 2:
                    spam_score = 0.0
                else:
                    spam_score = 2.0
            elif raw_score <= 4:
                spam_score = max(0.0, (raw_score - 1) * 0.5)
            else:
                # 6 to 9
                score_map = {6: 4.0, 7: 6.5, 8: 8.5, 9: 10.0}
                spam_score = score_map.get(raw_score, 5.0)

            return ScraperSourceResult(
                source_name=self.source_name,
                success=True,
                spam_score=round(spam_score, 1),
                search_count=search_count,
                report_count=len(comments),
                top_tags=tags[:3],
                comments=comments,
            )
        except Exception as exc:
            logger.debug("Error parsing Tellows HTML: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=f"Parser error: {exc}",
            )
