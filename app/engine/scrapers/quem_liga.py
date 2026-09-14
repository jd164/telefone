import re
import logging
from bs4 import BeautifulSoup
from app.engine.scrapers.base import BaseScraper
from app.models.schemas import ScraperSourceResult, CrowdsourcedComment

logger = logging.getLogger(__name__)


class QuemLigaScraper(BaseScraper):
    source_name: str = "Ligaram-me (Portugal)"

    async def query(self, e164: str, national_format: str) -> ScraperSourceResult:
        clean_num = re.sub(r"\D", "", e164)
        if clean_num.startswith("351"):
            national_num = clean_num[3:]
        else:
            national_num = clean_num

        url = f"https://ligaram-me.com/numero/{national_num}"
        html = await self.fetch_html(url)

        if not html:
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message="Sem resposta de Ligaram-me",
            )

        return self._parse_html(html)

    def _parse_html(self, html: str) -> ScraperSourceResult:
        try:
            soup = BeautifulSoup(html, "html.parser")
            lower_html = html.lower()

            # 1. Check if the number has NO reviews/comments
            has_no_reviews = (
                "ainda não tem qualquer comentário" in lower_html
                or "ainda não tem comentários" in lower_html
                or "seja o primeiro a comentar" in lower_html
            )

            # 2. Searches count
            search_count = 0
            search_matches = re.findall(r"(\d+[\d\s.,]*)\s*pesquisas", lower_html)
            if search_matches:
                num_str = re.sub(r"\D", "", search_matches[0])
                if num_str:
                    search_count = int(num_str)

            if has_no_reviews:
                # Clean, unflagged number with 0 complaints
                return ScraperSourceResult(
                    source_name=self.source_name,
                    success=True,
                    spam_score=0.0,
                    search_count=search_count,
                    report_count=0,
                    top_tags=[],
                    comments=[],
                )

            # 3. Extract Real User Comments (explicitly exclude forms, inputs, dropdowns)
            # Remove any comment-form or form blocks to prevent picking up option words like 'burla'
            for form in soup.find_all(class_=re.compile(r"form|select|dropdown", re.I)):
                form.decompose()

            comments = []
            comment_boxes = soup.find_all(class_=re.compile(r"comments__comment|detail\s*media|single[-_]?comment", re.I))
            for box in comment_boxes:
                comment_text = box.get_text(separator=" ", strip=True)
                # Filter out boilerplate
                if (
                    len(comment_text) > 15
                    and "ainda não tem qualquer comentário" not in comment_text.lower()
                    and "cookie" not in comment_text.lower()
                    and "privacidade" not in comment_text.lower()
                ):
                    comments.append(
                        CrowdsourcedComment(
                            source=self.source_name,
                            author="Utilizador Ligaram-me",
                            text=comment_text[:280],
                        )
                    )
                if len(comments) >= 3:
                    break

            if not comments:
                # No actual comments found
                return ScraperSourceResult(
                    source_name=self.source_name,
                    success=True,
                    spam_score=0.0,
                    search_count=search_count,
                    report_count=0,
                    top_tags=[],
                    comments=[],
                )

            # 4. Extract Tags ONLY from the actual user comments
            tags = []
            known_categories = [
                ("Burla MBWay", [r"\bmbway\b", r"\bmb\s*way\b", r"\bburla\s*mbway\b"]),
                ("Telemarketing", [r"\btelemarketing\b", r"\bvendas\b", r"\bcomercial\b", r"\bpromoção\b"]),
                ("Cobranças", [r"\bcobran[çc]a\b", r"\brecupera[çc][ãa]o\b", r"\bd[íi]vida\b"]),
                ("Chamada Silenciosa", [r"\bsilenciosa\b", r"\bping\s*call\b", r"\bdesliga\s*logo\b"]),
                ("Inquérito / Sondagem", [r"\binqu[ée]rito\b", r"\bsondagem\b", r"\bestudo\b"]),
            ]
            comments_blob = " ".join(c.text for c in comments).lower()
            for cat_name, patterns in known_categories:
                for pat in patterns:
                    if re.search(pat, comments_blob, re.I):
                        tags.append(cat_name)
                        break

            # 5. Detect Sentiment from actual user comments
            negative_indicators = len(re.findall(r"\b(negativ[oa]|perigoso|burla|fraude|spam|agressivo|burlão)\b", comments_blob, re.I))
            positive_indicators = len(re.findall(r"\b(seguro|leg[íi]timo|confi[áa]vel|positivo|amigo|família)\b", comments_blob, re.I))

            spam_score = 5.0
            if negative_indicators > positive_indicators:
                spam_score = min(10.0, 5.0 + min(negative_indicators, 5) * 1.0)
            elif positive_indicators > negative_indicators:
                spam_score = max(0.0, 5.0 - min(positive_indicators, 5) * 1.0)

            return ScraperSourceResult(
                source_name=self.source_name,
                success=True,
                spam_score=round(spam_score, 1),
                search_count=search_count,
                report_count=len(comments),
                top_tags=tags[:5],
                comments=comments,
            )
        except Exception as exc:
            logger.debug("Error parsing Ligaram-me HTML: %s", exc)
            return ScraperSourceResult(
                source_name=self.source_name,
                success=False,
                error_message=f"Parser error: {exc}",
            )
