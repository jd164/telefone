import asyncio
import json
import logging
import random
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Set
from bs4 import BeautifulSoup
import httpx
from sqlalchemy import select

from app.engine.scrapers.base import BaseScraper
from app.models.schemas import CommercialEntityInfo
from app.db.models import DorkCache
from app.db.session import AsyncSessionLocal
from app.core.observability import record_dork_debug

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/131.0.0.0 Safari/537.36",
]

GOV_POLICE_DOMAINS = {
    "psp.pt", "gnr.pt", "policiajudiciaria.pt", "gov.pt", "portugal.gov.pt",
    "sns.gov.pt", "sns24.gov.pt", "seg-social.pt", "portaldasfinancas.gov.pt",
    "justica.gov.pt", "inem.pt", "prociv.pt", "parlamento.pt", "presidencia.pt",
    "dgs.pt", "asae.gov.pt", "act.gov.pt", "bportugal.pt"
}

BUSINESS_REGISTRY_DOMAINS = {
    "paginasamarelas.pt", "pai.pt", "einforma.pt", "racius.com", "nif.pt",
    "igogo.pt", "guia-empresas.net", "hotfrog.pt", "infobel.com"
}


def detect_institutional_signal(snippet: str, title: str = "", url: str = "") -> Optional[Dict[str, Any]]:
    """
    Analyzes search engine result text (snippet + title + url) for institutional patterns
    such as 'PSP', 'GNR', 'Comando', 'Esquadra', 'Polícia de Segurança Pública',
    'Guarda Nacional Republicana', 'Divisão Policial', 'Posto Territorial', etc.
    Associates positive signal even if the originating URL is NOT an institutional domain
    (e.g., parish councils, news articles, municipal portals).
    """
    combined = f"{title} {snippet} {url}".strip()
    if not combined:
        return None

    lower_text = combined.lower()

    institutional_patterns = [
        # PSP patterns
        (r"\b(?:pol[íi]cia\s+de\s+seguran[çc]a\s+p[úu]blica|psp|cometlis|cometpor)\b", "PSP", "Polícia de Segurança Pública (PSP)"),
        (r"\b(?:esquadra|divis[ãa]o\s+policial|comissariado|esquadra\s+de\s+tr[âa]nsito)\b", "PSP", "Esquadra / Divisão Policial (PSP)"),

        # GNR patterns
        (r"\b(?:guarda\s+nacional\s+republicana|gnr)\b", "GNR", "Guarda Nacional Republicana (GNR)"),
        (r"\b(?:posto\s+territorial|destacamento\s+territorial|posto\s+da\s+gnr|comando\s+territorial)\b", "GNR", "Posto / Destacamento Territorial (GNR)"),

        # Judicial & Municipal Police
        (r"\b(?:pol[íi]cia\s+judici[áa]ria|pj)\b", "PJ", "Polícia Judiciária (PJ)"),
        (r"\b(?:pol[íi]cia\s+municipal)\b", "POLICIA_MUNICIPAL", "Polícia Municipal"),
        (r"\b(?:comando\s+distrital|comando\s+metropolitano|for[çc]as?\s+de\s+seguran[çc]a|pol[íi]cia)\b", "POLICIA", "Força Policial / Comando"),

        # Emergency & Hospitals
        (r"\b(?:inem|prote[çc][ãa]o\s+civil|bombeiros|sns\s*24|sa[úu]de\s*24)\b", "EMERGENCIA", "Serviço de Emergência / Proteção Civil"),
        (r"\b(?:centro\s+hospitalar|hospital\s+distrital|hospital\s+de|unidade\s+local\s+de\s+sa[úu]de|uls)\b", "HOSPITAL", "Unidade de Saúde / Hospital Público"),
        (r"\b(?:c[âa]mara\s+municipal|junta\s+de\s+freguesia|tribunal\s+judicial|conservat[óo]ria)\b", "ADMINISTRACAO_PUBLICA", "Serviço Público / Administração Local"),
    ]

    for pattern, entity_type, default_name in institutional_patterns:
        m = re.search(pattern, lower_text)
        if m:
            clean_title = re.sub(r"\s*[-|–—].*$", "", title).strip()
            entity_name = clean_title if len(clean_title) >= 4 else default_name
            is_police = entity_type in ("PSP", "GNR", "PJ", "POLICIA", "POLICIA_MUNICIPAL")
            return {
                "entity_type": entity_type,
                "matched_pattern": m.group(0),
                "matched_regex": pattern,
                "entity_name": entity_name,
                "is_police": is_police,
                "category": "Polícia / Segurança Pública" if is_police else "Serviço Público Governamental",
            }

    # Fallback to institutional domain check
    is_gov_domain = any(dom in url.lower() for dom in GOV_POLICE_DOMAINS)
    if is_gov_domain:
        clean_title = re.sub(r"\s*[-|–—].*$", "", title).strip()
        is_police = any(k in url.lower() for k in ["psp", "gnr", "policia"])
        return {
            "entity_type": "GOV",
            "matched_pattern": "gov_domain",
            "matched_regex": "domain",
            "entity_name": clean_title or "Entidade Governamental Oficial",
            "is_police": is_police,
            "category": "Polícia / Segurança Pública" if is_police else "Serviço Público Governamental",
        }

    return None


class SearchDorkEngine(BaseScraper):
    """
    Robust OSINT Search Engine Dorking without paid APIs.
    Executes broad non-domain-restricted dorks concurrently across DuckDuckGo HTML,
    Brave Search HTML, and Bing fallback, with institutional signal detection,
    consensus scoring (1 source -> MEDIUM, 2+ sources -> HIGH), per-number debug logging,
    and 30-day SQLite caching.
    """

    source_name: str = "Dork Engine (DuckDuckGo HTML / Brave Search / OSINT)"

    async def search_dorks(self, e164: str, national_format: str) -> Optional[CommercialEntityInfo]:
        clean_num = re.sub(r"\D", "", e164)
        clean_nat = clean_num[3:] if clean_num.startswith("351") else clean_num
        spaced_nat = f"{clean_nat[:3]} {clean_nat[3:6]} {clean_nat[6:]}" if len(clean_nat) == 9 else clean_nat

        # 1. Check local SQLite cache first (TTL 30 days)
        cached_info = await self._get_cached_dork(e164)
        if cached_info is not None:
            logger.debug("Dork cache hit for %s", e164)
            return cached_info

        # 2. Add randomized jitter delay to prevent rate-limiting
        await asyncio.sleep(random.uniform(0.1, 0.3))

        # 3. Build broad dork queries without domain restrictions + targeted site queries
        queries = [
            f'"{clean_nat}" PSP',
            f'"{clean_nat}" GNR',
            f'"{clean_nat}" esquadra',
            f'"{clean_nat}" "comando distrital"',
            f'"{clean_nat}" polícia',
            f'"{clean_nat}" (site:gov.pt OR site:psp.pt OR site:gnr.pt OR site:sns.gov.pt OR site:seg-social.pt)',
            f'"{clean_nat}" (site:paginasamarelas.pt OR site:einforma.pt OR site:racius.com OR site:nif.pt)',
            f'"{spaced_nat}" PSP',
        ]

        # 4. Execute queries concurrently across available free HTML engines
        all_raw_results: List[Dict[str, Any]] = []

        async def fetch_query_results(q: str) -> List[Dict[str, Any]]:
            # Try DuckDuckGo first
            ddg_res = await self._query_duckduckgo_html(q)
            if ddg_res:
                return ddg_res

            # Fallback to Brave
            brave_res = await self._query_brave_html(q)
            if brave_res:
                return brave_res

            # Fallback to Bing
            bing_res = await self._query_bing_html(q)
            if bing_res:
                return bing_res

            return []

        # Run primary broad queries in parallel with an overall timeout of 6.0s
        primary_queries = queries[:4]
        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*(fetch_query_results(q) for q in primary_queries), return_exceptions=True),
                timeout=6.0,
            )
            for g in gathered:
                if isinstance(g, list):
                    all_raw_results.extend(g)
        except asyncio.TimeoutError:
            logger.debug("Dork engine parallel queries timed out after 6.0s")


        # 5. Deduplicate results by URL domain or unique URL
        unique_results: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for item in all_raw_results:
            href = item.get("href", "")
            title = item.get("title", "")
            # Deduplication key based on normalized domain and path or title
            parsed_url = urllib.parse.urlparse(href)
            domain = parsed_url.netloc.lower() or "unknown"
            key = f"{domain}:{title[:30]}"
            if key not in seen_keys:
                seen_keys.add(key)
                item["domain"] = domain
                unique_results.append(item)

        # 6. Run institutional signal detector over all extracted items
        agreeing_sources: Dict[str, Dict[str, Any]] = {}
        detected_signals: List[Dict[str, Any]] = []
        biz_match: Optional[Dict[str, Any]] = None

        for item in unique_results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            href = item.get("href", "")
            domain = item.get("domain", "")

            signal = detect_institutional_signal(snippet=snippet, title=title, url=href)
            if signal:
                detected_signals.append({
                    "title": title,
                    "snippet": snippet,
                    "url": href,
                    "domain": domain,
                    "signal": signal,
                })
                # Register independent agreeing domain
                if domain not in agreeing_sources:
                    agreeing_sources[domain] = {
                        "signal": signal,
                        "title": title,
                        "snippet": snippet,
                        "url": href,
                    }
            elif not biz_match:
                # Check for business directory match (Páginas Amarelas, Racius, eInforma)
                is_pa = any(pa in href.lower() for pa in BUSINESS_REGISTRY_DOMAINS)
                if is_pa or "empresa" in f"{title} {snippet}".lower():
                    clean_name = re.sub(r"\s*[-|–—].*$", "", title).strip()
                    if len(clean_name) >= 3:
                        biz_match = {
                            "name": clean_name,
                            "website": href,
                            "snippet": f"{title}: {snippet[:200]}",
                        }

        # 7. Consensus & Confidence Calculation
        final_info: Optional[CommercialEntityInfo] = None
        consensus_domains = list(agreeing_sources.keys())
        consensus_count = len(consensus_domains)

        if consensus_count >= 1:
            # Pick the most representative entity name
            sample_entry = next(iter(agreeing_sources.values()))
            sample_signal = sample_entry["signal"]
            
            # Prefer a title that mentions the city or district or station
            best_name = sample_signal["entity_name"]
            for d_info in agreeing_sources.values():
                t = d_info["title"]
                if any(kw in t.lower() for kw in ["esquadra", "posto", "comando", "divisão"]):
                    best_name = re.sub(r"\s*[-|–—].*$", "", t).strip()
                    break

            primary_website = sample_entry["url"]
            evidence = [f"[{d}] {info['title']}: {info['snippet'][:180]}" for d, info in agreeing_sources.items()]

            is_police = any(d_info["signal"].get("is_police", False) for d_info in agreeing_sources.values())
            category = "Polícia / Segurança Pública" if is_police else sample_signal["category"]

            if consensus_count >= 2:
                # 2+ independent sources agree -> HIGH confidence, consensus
                final_info = CommercialEntityInfo(
                    is_commercial_entity=True,
                    entity_name=best_name,
                    category=category,
                    website=primary_website,
                    address="Portugal",
                    evidence_snippets=evidence[:4],
                    confidence="HIGH",
                    matched_by="dork_consensus",
                    consensus_count=consensus_count,
                )
            else:
                # 1 source confirms -> MEDIUM confidence, inference
                final_info = CommercialEntityInfo(
                    is_commercial_entity=True,
                    entity_name=best_name,
                    category=category,
                    website=primary_website,
                    address="Portugal",
                    evidence_snippets=evidence[:4],
                    confidence="MEDIUM",
                    matched_by="dork_inference",
                    consensus_count=1,
                )
        elif biz_match:
            # Commercial directory inference
            final_info = CommercialEntityInfo(
                is_commercial_entity=True,
                entity_name=biz_match["name"],
                category="Empresa Registada (Páginas Amarelas / Diretório)",
                website=biz_match["website"],
                address="Portugal",
                evidence_snippets=[biz_match["snippet"]],
                confidence="MEDIUM",
                matched_by="dork_inference",
                consensus_count=1,
            )

        # 8. Record structured debug log to data/dork_debug/<clean_phone>.json
        record_dork_debug(
            phone_e164=e164,
            queries=queries,
            raw_results=unique_results,
            detected_signals=detected_signals,
            matched=final_info is not None and final_info.is_commercial_entity,
            matched_by=final_info.matched_by if final_info else None,
            consensus_sources=consensus_domains,
        )

        # 9. Save to SQLite cache (TTL 30 days)
        await self._save_cached_dork(e164, final_info)

        return final_info

    async def _query_duckduckgo_html(self, query: str) -> List[Dict[str, str]]:
        """Scrapes DuckDuckGo HTML endpoint (html.duckduckgo.com/html/) directly."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}&kl=pt-pt"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="131", "Google Chrome";v="131"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }

        results: List[Dict[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=2.8, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code != 200 or not resp.text or "anomaly.js" in resp.text:
                    # Retry with POST if GET returned challenge
                    resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query, "b": "", "kl": "pt-pt"})

                if resp.status_code == 200 and resp.text and "anomaly.js" not in resp.text:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("div", class_=re.compile(r"result__body|links_main|web-result"))
                    for item in items[:4]:
                        title_elem = item.find("a", class_=re.compile(r"result__a|result__title")) or item.find("a")
                        title = title_elem.get_text(strip=True) if title_elem else ""
                        href = title_elem.get("href", "") if title_elem else ""
                        snippet_elem = item.find("a", class_=re.compile(r"result__snippet")) or item.find("div", class_=re.compile(r"result__snippet"))
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                        if title:
                            results.append({"title": title, "snippet": snippet, "href": href, "engine": "duckduckgo"})
        except Exception as exc:
            logger.debug("DuckDuckGo HTML query error: %s", exc)

        return results

    async def _query_brave_html(self, query: str) -> List[Dict[str, str]]:
        """Fallback search using Brave Search HTML."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://search.brave.com/search?q={encoded}&source=web"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        }

        results: List[Dict[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=2.8, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.text:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("div", class_=re.compile(r"snippet|result"))
                    for item in items[:4]:
                        title_elem = item.find(["a", "div"], class_=re.compile(r"title|heading"))
                        title = title_elem.get_text(strip=True) if title_elem else ""
                        link = item.find("a")
                        href = link.get("href", "") if link else ""
                        snippet_elem = item.find("div", class_=re.compile(r"snippet-description|content"))
                        snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                        if title:
                            results.append({"title": title, "snippet": snippet, "href": href, "engine": "brave"})
        except Exception as exc:
            logger.debug("Brave HTML query fallback error: %s", exc)

        return results

    async def _query_bing_html(self, query: str) -> List[Dict[str, str]]:
        """Additional free search fallback using Bing HTML."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.bing.com/search?q={encoded}&setlang=pt-pt"
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        }

        results: List[Dict[str, str]] = []
        try:
            async with httpx.AsyncClient(timeout=2.8, follow_redirects=True, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.text:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("li", class_="b_algo")
                    for item in items[:4]:
                        h2 = item.find("h2")
                        title = h2.get_text(strip=True) if h2 else ""
                        a = h2.find("a") if h2 else None
                        href = a.get("href", "") if a else ""
                        p = item.find("p")
                        snippet = p.get_text(strip=True) if p else ""

                        if title:
                            results.append({"title": title, "snippet": snippet, "href": href, "engine": "bing"})
        except Exception as exc:
            logger.debug("Bing HTML query fallback error: %s", exc)

        return results

    async def _get_cached_dork(self, phone_e164: str) -> Optional[CommercialEntityInfo]:
        try:
            async with AsyncSessionLocal() as session:
                query = select(DorkCache).where(
                    DorkCache.phone_e164 == phone_e164,
                    DorkCache.expires_at > datetime.now(timezone.utc),
                )
                res = await session.execute(query)
                entry = res.scalars().first()
                if entry and entry.data_json:
                    data = json.loads(entry.data_json)
                    if not data.get("is_commercial_entity"):
                        return None
                    return CommercialEntityInfo(**data)
        except Exception as exc:
            logger.debug("Dork cache lookup error: %s", exc)

        return None

    async def _save_cached_dork(self, phone_e164: str, info: Optional[CommercialEntityInfo]):
        try:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(days=30)
            data_dict = info.model_dump() if info else {"is_commercial_entity": False}

            async with AsyncSessionLocal() as session:
                cached = DorkCache(
                    phone_e164=phone_e164,
                    created_at=now,
                    expires_at=expires,
                    data_json=json.dumps(data_dict, ensure_ascii=False),
                )
                await session.merge(cached)
                await session.commit()
        except Exception as exc:
            logger.debug("Dork cache save error: %s", exc)

    async def query(self, e164: str, national_format: str):
        return await self.search_dorks(e164, national_format)
