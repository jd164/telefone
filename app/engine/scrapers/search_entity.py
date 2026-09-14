import re
import urllib.parse
import logging
from typing import Optional
from bs4 import BeautifulSoup
from app.engine.scrapers.base import BaseScraper
from app.models.schemas import CommercialEntityInfo
from app.core.config import settings

logger = logging.getLogger(__name__)

# Domains that are only spam reputation forums, not actual business websites
SPAM_DOMAINS_BLACKLIST = {
    "tellows.pt", "tellows.com", "ligaram-me.com", "quem-liga.com", "shouldianswer.net",
    "devolva-me.com", "desconhecido.com", "who-called.co.uk", "sync.me", "truecaller.com",
    "telefonaspam.es", "callfilter.app", "spamcalls.net"
}


class CommercialEntityVerifier(BaseScraper):
    source_name: str = "Commercial Entity Verifier"

    async def verify_entity(self, e164: str, national_format: str) -> CommercialEntityInfo:
        # Check Google Places first if configured
        if settings.GOOGLE_PLACES_API_KEY:
            places_result = await self._query_google_places(e164)
            if places_result and places_result.is_commercial_entity:
                return places_result

        # DuckDuckGo HTML Search
        return await self._query_duckduckgo(e164, national_format)

    async def _query_google_places(self, phone: str) -> Optional[CommercialEntityInfo]:
        encoded_phone = urllib.parse.quote_plus(phone)
        url = (
            f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
            f"?input={encoded_phone}&inputtype=phonenumber"
            f"&fields=name,formatted_address,types,business_status,website"
            f"&key={settings.GOOGLE_PLACES_API_KEY}"
        )
        try:
            import httpx, json
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        c = candidates[0]
                        return CommercialEntityInfo(
                            is_commercial_entity=True,
                            entity_name=c.get("name"),
                            category=", ".join(c.get("types", [])),
                            address=c.get("formatted_address"),
                            website=c.get("website"),
                            evidence_snippets=["Perfil empresarial verificado no Google Places / Maps."],
                        )
        except Exception as exc:
            logger.debug("Google Places API error: %s", exc)
        return None

    async def _query_duckduckgo(self, e164: str, national_format: str) -> CommercialEntityInfo:
        # Search query matching exact phone string
        clean_nat = re.sub(r"\s+", " ", national_format.strip())
        query = f'"{e164}" OR "{clean_nat}"'
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        html = await self.fetch_html(url)
        if not html:
            return CommercialEntityInfo(is_commercial_entity=False)

        return self._parse_search_results(html, e164, national_format)

    def _parse_search_results(self, html: str, e164: str, national_format: str) -> CommercialEntityInfo:
        try:
            soup = BeautifulSoup(html, "html.parser")
            results = soup.find_all(class_=re.compile(r"result__body|result\s"))

            evidence = []
            candidate_names = []
            found_website = None

            business_keywords = [
                r"empresa", r"loja", r"hospital", r"cl[íi]nica", r"farm[áa]cia", r"banco",
                r"restaurante", r"hotel", r"advogad[oa]", r"not[áa]rio", r"seguros",
                r"oficina", r"consult[óo]rio", r"escola", r"universidade", r"servi[çc]o oficial",
                r"c[âa]mara municipal", r"junta de freguesia", r"ctt", r"santander", r"millennium",
                r"novo banco", r"caixa geral", r"edp", r"galp", r"via verde", r"doutor finanças"
            ]

            for r in results[:8]:
                title_elem = r.find(class_=re.compile(r"result__title|result__a"))
                snippet_elem = r.find(class_=re.compile(r"result__snippet"))
                url_elem = r.find(class_=re.compile(r"result__url"))

                title = title_elem.get_text(strip=True) if title_elem else ""
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                link_text = url_elem.get_text(strip=True) if url_elem else ""

                combined = f"{title} {snippet}".lower()

                # Check if it's a known spam forum
                is_spam_site = any(blacklisted in link_text.lower() or blacklisted in combined for blacklisted in SPAM_DOMAINS_BLACKLIST)
                if is_spam_site:
                    continue

                # Check for business indicators
                has_biz_match = any(re.search(rf"\b{kw}\b", combined) for kw in business_keywords)
                if has_biz_match and (title or snippet):
                    clean_snippet = snippet[:220] if snippet else title[:220]
                    evidence.append(f"{title}: {clean_snippet}")
                    if not found_website and link_text and not is_spam_site:
                        found_website = link_text.strip()
                    # Clean title to extract entity name
                    cleaned_name = re.sub(r"\s*[-|–].*$", "", title).strip()
                    if len(cleaned_name) > 3 and not any(ch in cleaned_name for ch in ["+", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]):
                        candidate_names.append(cleaned_name)

            if evidence:
                best_name = candidate_names[0] if candidate_names else None
                return CommercialEntityInfo(
                    is_commercial_entity=True,
                    entity_name=best_name,
                    website=found_website,
                    evidence_snippets=evidence[:3],
                )

            return CommercialEntityInfo(is_commercial_entity=False)
        except Exception as exc:
            logger.debug("Error parsing search results: %s", exc)
            return CommercialEntityInfo(is_commercial_entity=False)

    async def query(self, e164: str, national_format: str):
        # Implementation of abstract BaseScraper method
        return await self.verify_entity(e164, national_format)
