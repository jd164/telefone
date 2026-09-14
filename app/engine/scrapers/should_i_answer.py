import re
import logging
from bs4 import BeautifulSoup
from app.engine.scrapers.base import BaseScraper
from app.models.schemas import ScraperSourceResult, CrowdsourcedComment

logger = logging.getLogger(__name__)


class ShouldIAnswerScraper(BaseScraper):
    source_name: str = "Should I Answer (Devo Atender)"

    async def query(self, e164: str, national_format: str) -> ScraperSourceResult:
        clean_num = re.sub(r"\D", "", e164)
        if clean_num.startswith("351"):
            nat = clean_num[3:]
            url = f"https://pt.shouldianswer.net/numero-de-telefone/0{nat}"
        else:
            url = f"https://www.shouldianswer.net/phone-number/{clean_num}"

        html = await self.fetch_html(url)
        if not html:
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message="Sem resposta de Should I Answer",
            )

        return self._parse_html(html)

    def _parse_html(self, html: str) -> ScraperSourceResult:
        try:
            soup = BeautifulSoup(html, "html.parser")
            text = html.lower()

            # Check if there are no reports
            if "não reunimos muita informação sobre este número" in text or "ainda não há avaliações" in text:
                return ScraperSourceResult(
                    source_name=self.source_name,
                    success=True,
                    spam_score=0.0,
                    search_count=0,
                    report_count=0,
                    top_tags=[],
                    comments=[],
                )

            # Check explicit rating
            spam_score = 0.0
            tags = []
            if "muito negativa" in text:
                spam_score = 9.5
                tags.append("Muito Negativa")
            elif "negativa" in text and "não negativa" not in text:
                spam_score = 7.5
                tags.append("Negativa / Indesejada")
            elif "neutra" in text:
                spam_score = 2.0
                tags.append("Neutra")
            elif "positiva" in text:
                spam_score = 0.0
                tags.append("Seguro / Positiva")

            # Check reviews count
            reviews_count = 0
            rev_matches = re.findall(r"(\d+)\s*resenhas", text)
            if rev_matches:
                reviews_count = int(rev_matches[0])

            # Extract user reviews
            comments = []
            review_elements = soup.find_all(class_=re.compile(r"reviewItem|singleReview|commentBody", re.I))
            for rev in review_elements[:3]:
                rev_text = rev.get_text(separator=" ", strip=True)
                if len(rev_text) > 10 and "devo atender" not in rev_text.lower():
                    comments.append(
                        CrowdsourcedComment(
                            source=self.source_name,
                            author="Utilizador ShouldIAnswer",
                            text=rev_text[:280],
                        )
                    )

            return ScraperSourceResult(
                source_name=self.source_name,
                success=True,
                spam_score=spam_score,
                search_count=max(reviews_count, 1) if reviews_count > 0 else 0,
                report_count=reviews_count,
                top_tags=tags,
                comments=comments,
            )
        except Exception as exc:
            logger.debug("Error parsing Should I Answer HTML: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=str(exc),
            )
