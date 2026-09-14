import asyncio
import json
import logging
import random
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from collections import defaultdict
from bs4 import BeautifulSoup
import httpx

from app.engine.anacom import anacom_db
from app.engine.trusted_directory import paginas_amarelas_db

logger = logging.getLogger(__name__)

PAGINAS_AMARELAS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "paginas_amarelas_pt.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Baseline seed blocks for major Portuguese districts and national services
SEED_INSTITUTIONAL_BLOCKS: List[Dict[str, Any]] = [
    # Lisboa (21)
    {"block": "21765", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Direção Nacional / Cometlis"},
    {"block": "21342", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Lisboa 1ª Divisão (Baixa)"},
    {"block": "21322", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Lisboa 2ª Divisão (Rato)"},
    {"block": "21771", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Lisboa 3ª Divisão (Benfica)"},
    {"block": "21841", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Lisboa 4ª Divisão (Olivais)"},
    {"block": "21854", "district": "Lisboa", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Lisboa Aeroporto / Trânsito"},
    {"block": "21434", "district": "Lisboa / Amadora", "type": "Polícia / Saúde Pública", "entity_hint": "PSP Amadora / Hospital Fernando Fonseca"},
    {"block": "21484", "district": "Lisboa / Cascais", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Cascais / Estoril"},
    {"block": "21923", "district": "Lisboa / Sintra", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Sintra / Mem Martins"},
    {"block": "21932", "district": "Lisboa / Odivelas", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial de Odivelas"},
    {"block": "21983", "district": "Lisboa / Loures", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial de Loures"},
    {"block": "21321", "district": "Lisboa", "type": "Guarda Nacional Republicana (GNR)", "entity_hint": "GNR Comando Geral / Unidades Centrais"},
    {"block": "21780", "district": "Lisboa", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital de Santa Maria / CHULN"},
    {"block": "21817", "district": "Lisboa", "type": "Administração Local / Autarquia", "entity_hint": "Câmara Municipal de Lisboa"},
    {"block": "21196", "district": "Lisboa", "type": "Polícia Judiciária (PJ)", "entity_hint": "Polícia Judiciária Direção Nacional"},
    {"block": "21720", "district": "Lisboa", "type": "Autoridade Tributária / Estado", "entity_hint": "Autoridade Tributária (Finanças)"},
    {"block": "21047", "district": "Nacional / Lisboa", "type": "Serviço Postal Oficial", "entity_hint": "CTT - Correios de Portugal"},
    {"block": "21054", "district": "Nacional / Lisboa", "type": "Segurança Social", "entity_hint": "Instituto da Segurança Social"},
    {"block": "21294", "district": "Setúbal / Almada", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital Garcia de Orta Almada"},
    {"block": "21272", "district": "Setúbal / Almada", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital Garcia de Orta Consultas"},

    # Porto (22)
    {"block": "22209", "district": "Porto", "type": "Força Policial / Autarquia", "entity_hint": "PSP Porto Comando / Câmara do Porto"},
    {"block": "22207", "district": "Porto", "type": "Guarda Nacional Republicana (GNR)", "entity_hint": "GNR Porto / Hospital Santo António"},
    {"block": "22619", "district": "Porto", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Porto 1ª Divisão (Foz)"},
    {"block": "22519", "district": "Porto", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Porto 2ª Divisão (Bomfim)"},
    {"block": "22508", "district": "Porto", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Porto 3ª Divisão (Paranhos)"},
    {"block": "22551", "district": "Porto", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital de São João (CHSJ)"},
    {"block": "22938", "district": "Porto / Matosinhos", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial de Matosinhos"},
    {"block": "22466", "district": "Porto / Gondomar", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial de Gondomar"},
    {"block": "22941", "district": "Porto / Maia", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial da Maia"},
    {"block": "22377", "district": "Porto / Vila Nova de Gaia", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Divisão Policial de Gaia"},

    # Coimbra (239)
    {"block": "23985", "district": "Coimbra", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Coimbra"},
    {"block": "23979", "district": "Coimbra", "type": "Guarda Nacional Republicana (GNR)", "entity_hint": "GNR Comando Territorial de Coimbra"},
    {"block": "23940", "district": "Coimbra", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospitais da Univ. de Coimbra (CHUC)"},

    # Braga (253)
    {"block": "25320", "district": "Braga", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Braga"},
    {"block": "25360", "district": "Braga", "type": "Guarda Nacional Republicana (GNR)", "entity_hint": "GNR Comando Territorial de Braga"},
    {"block": "25302", "district": "Braga", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital de Braga"},

    # Setúbal (265)
    {"block": "26553", "district": "Setúbal", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Setúbal"},
    {"block": "26554", "district": "Setúbal", "type": "Força de Segurança / Hospital", "entity_hint": "GNR Setúbal / Hospital São Bernardo"},

    # Faro (289)
    {"block": "28989", "district": "Faro / Algarve", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Faro"},
    {"block": "28988", "district": "Faro / Algarve", "type": "Guarda Nacional Republicana (GNR)", "entity_hint": "GNR Comando Territorial de Faro"},
    {"block": "28980", "district": "Faro / Algarve", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital de Faro (CHUA Algarve)"},

    # Aveiro (234)
    {"block": "23437", "district": "Aveiro", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Aveiro / GNR Aveiro / Hospital"},

    # Leiria (244)
    {"block": "24485", "district": "Leiria", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Leiria"},
    {"block": "24481", "district": "Leiria", "type": "Serviço Nacional de Saúde (Hospital)", "entity_hint": "Hospital de Santo André Leiria"},

    # Santarém (243)
    {"block": "24330", "district": "Santarém", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Santarém / GNR Santarém / Hospital"},

    # Viseu (232)
    {"block": "23248", "district": "Viseu", "type": "Polícia de Segurança Pública (PSP)", "entity_hint": "PSP Comando Distrital de Viseu"},

    # Viana do Castelo (258)
    {"block": "25880", "district": "Viana do Castelo", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Viana do Castelo / GNR Viana"},

    # Vila Real (259)
    {"block": "25930", "district": "Vila Real", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Vila Real / GNR Vila Real"},

    # Bragança (273)
    {"block": "27330", "district": "Bragança", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Bragança / GNR Bragança"},

    # Guarda (271)
    {"block": "27120", "district": "Guarda", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Guarda / GNR Guarda"},

    # Castelo Branco (272)
    {"block": "27233", "district": "Castelo Branco", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Castelo Branco / GNR Castelo Branco"},

    # Portalegre (245)
    {"block": "24530", "district": "Portalegre", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Portalegre / GNR Portalegre"},

    # Évora (266)
    {"block": "26676", "district": "Évora", "type": "Força de Segurança (PSP/GNR)", "entity_hint": "PSP Comando Distrital de Évora / GNR"},

    # Beja (284)
    {"block": "28431", "district": "Beja", "type": "Força de Segurança (PSP/GNR)", "entity_hint": "PSP Comando Distrital de Beja / GNR"},

    # Madeira (291)
    {"block": "29120", "district": "Funchal (Madeira)", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Madeira / Hospital Dr. Nélio Mendonça"},

    # Açores (296, 295, 292)
    {"block": "29620", "district": "Ponta Delgada (Açores)", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Açores / Hospital Divino Espírito Santo"},
    {"block": "29520", "district": "Angra do Heroísmo (Açores)", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Angra / Hospital Santo Espírito"},
    {"block": "29220", "district": "Horta (Açores)", "type": "Força de Segurança / Saúde", "entity_hint": "PSP Horta / Hospital da Horta"},

    # Linhas Nacionais
    {"block": "30051", "district": "Nacional", "type": "Serviço Público / Segurança Social", "entity_hint": "Linha Segurança Social"},
    {"block": "80824", "district": "Nacional", "type": "Saúde / Emergência Pública", "entity_hint": "SNS 24"},
    {"block": "80850", "district": "Nacional", "type": "Serviço Essencial de Utilidade Pública", "entity_hint": "Linhas de Utilidade Pública"},
]

PORTUGAL_DISTRICTS = [
    "Lisboa", "Porto", "Coimbra", "Braga", "Setúbal", "Faro", "Aveiro",
    "Leiria", "Santarém", "Viseu", "Viana do Castelo", "Vila Real", "Bragança",
    "Guarda", "Castelo Branco", "Portalegre", "Évora", "Beja", "Madeira", "Açores"
]


class GeographicMatcher:
    """
    Dynamic Institutional Prefix Matcher.
    Auto-derives institutional blocks of 4 and 5 digits from confirmed numbers in the trusted directory,
    and clusters stations by district. When an unlisted station shares a 5-digit block with confirmed stations,
    it dynamically infers it as a probable police station or public service with MEDIUM confidence.
    """

    def __init__(self):
        self._seed_blocks = {b["block"]: b for b in SEED_INSTITUTIONAL_BLOCKS}
        self.active_blocks: Dict[str, Dict[str, Any]] = {}
        self.rebuild_dynamic_blocks()

    def rebuild_dynamic_blocks(self):
        """
        Scans all confirmed entries in `paginas_amarelas_db`.
        Groups numbers by 5-digit prefix and extracts institutional clusters.
        Any 5-digit prefix with >=2 institutional numbers (or >=1 police/hospital seed)
        automatically becomes an institutional block for that district.
        """
        # Start with seeds
        merged_blocks: Dict[str, Dict[str, Any]] = dict(self._seed_blocks)

        # Prefix clustering: prefix_5 -> list of entries
        prefix_clusters = defaultdict(list)
        all_entries = paginas_amarelas_db.get_all_confirmed_numbers()

        for item in all_entries:
            raw_num = re.sub(r"\D", "", str(item.get("number", "")))
            clean_nat = raw_num[3:] if raw_num.startswith("351") else raw_num
            if len(clean_nat) >= 5:
                p5 = clean_nat[:5]
                prefix_clusters[p5].append(item)

        # Evaluate clusters
        for prefix, items in prefix_clusters.items():
            # Check how many are official/police/health
            official_items = [
                it for it in items
                if any(k in (it.get("name", "") + " " + it.get("category", "")).lower()
                       for k in ["psp", "polícia", "gnr", "esquadra", "hospital", "saúde", "câmara municipal", "tribunal"])
            ]

            # Rule: If >=2 official items, or if already seeded, form a dynamic institutional block
            if len(official_items) >= 2 or (prefix in merged_blocks and len(official_items) >= 1):
                first = official_items[0]
                name_sample = first.get("name", "Entidade Oficial")
                cat_sample = first.get("category", "Força de Segurança / Serviço Público")
                address_sample = first.get("address", "Portugal")

                # Look up district via ANACOM prefix
                anacom_res = anacom_db.lookup(f"+351{prefix}0000"[:13])
                district = anacom_res.geographic_area if anacom_res and anacom_res.geographic_area else address_sample

                clean_entity_hint = re.sub(r"\s*\(.*?\)", "", name_sample).strip()

                merged_blocks[prefix] = {
                    "block": prefix,
                    "district": district,
                    "type": cat_sample,
                    "entity_hint": f"{clean_entity_hint} / Bloco Institucional ({district})",
                    "auto_generated": prefix not in self._seed_blocks,
                    "confirmed_stations_count": len(official_items),
                }

        self.active_blocks = merged_blocks
        logger.info("Dynamic institutional blocks rebuilt. Total active blocks: %d", len(self.active_blocks))

    def match_institutional_range(self, e164: str, national_digits: str) -> Optional[Dict[str, Any]]:
        clean_num = re.sub(r"\D", "", e164)
        clean_nat = clean_num[3:] if clean_num.startswith("351") else clean_num
        if not clean_nat and national_digits:
            clean_nat = re.sub(r"\D", "", national_digits)

        if not clean_nat:
            return None

        # Check longest block first
        sorted_prefixes = sorted(self.active_blocks.keys(), key=lambda k: len(k), reverse=True)
        for prefix in sorted_prefixes:
            if clean_nat.startswith(prefix):
                entry = self.active_blocks[prefix]
                anacom_res = anacom_db.lookup(e164 if e164.startswith("+") else f"+351{clean_nat}")
                geo_area = anacom_res.geographic_area if anacom_res and anacom_res.geographic_area else entry["district"]

                return {
                    "is_matched": True,
                    "matched_block": prefix,
                    "district": geo_area,
                    "institution_type": entry["type"],
                    "entity_hint": entry["entity_hint"],
                    "confidence": "MEDIUM",
                    "matched_by": "geographic_prefix_inference",
                    "probable_category": f"Possível Força de Segurança / Serviço Público ({geo_area})",
                    "description": f"Número pertencente ao bloco institucional alocado a {entry['entity_hint']}.",
                }

        return None

    def get_coverage_report(self) -> Dict[str, Any]:
        """
        Generates a district-by-district breakdown of coverage:
        - HIGH matches (exact stations in trusted_directory)
        - MEDIUM matches (active 5-digit institutional blocks)
        - Coverage rating.
        """
        report_by_district: Dict[str, Dict[str, Any]] = {}
        all_entries = paginas_amarelas_db.get_all_confirmed_numbers()

        for dist in PORTUGAL_DISTRICTS:
            # Count exact entries for this district
            exact_count = 0
            for item in all_entries:
                addr = (item.get("address") or "").lower()
                name = (item.get("name") or "").lower()
                dist_l = dist.lower()
                if dist_l in addr or dist_l in name:
                    exact_count += 1

            # Count dynamic blocks for this district
            blocks_count = 0
            for blk in self.active_blocks.values():
                b_dist = (blk.get("district") or "").lower()
                if dist.lower() in b_dist:
                    blocks_count += 1

            if exact_count >= 8:
                rating = "EXCELENTE"
            elif exact_count >= 3 or blocks_count >= 2:
                rating = "BOA"
            elif exact_count >= 1 or blocks_count >= 1:
                rating = "MODERADA"
            else:
                rating = "GAP_DETETADO"

            report_by_district[dist] = {
                "exact_stations_high": exact_count,
                "dynamic_blocks_medium": blocks_count,
                "coverage_status": rating,
            }

        return {
            "total_districts_monitored": len(PORTUGAL_DISTRICTS),
            "total_active_blocks": len(self.active_blocks),
            "total_confirmed_entities": len(all_entries),
            "districts": report_by_district,
        }


class PoliceDirectoryScraper:
    """
    Robust, verifiable background scraper querying public contact directories of PSP and GNR
    without paid APIs. Emits structured log 'INFO: scraped N esquadras, M falharam' and updates the database.
    """

    def __init__(self, output_file: Path = PAGINAS_AMARELAS_FILE):
        self.output_file = output_file
        self.last_scraped_count = 0
        self.last_failed_count = 0

    async def run_discovery_cycle(self) -> Dict[str, int]:
        """
        Executes an asynchronous scraping run against public police contact directories.
        Returns {'scraped': N, 'failed': M}.
        """
        discovered_entries: List[Dict[str, Any]] = []
        failed_count = 0

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        }

        # Public directory target pages
        targets = [
            ("https://www.psp.pt/Pages/contactos.aspx", "PSP"),
            ("https://www.psp.pt/Pages/onde-estamos.aspx", "PSP"),
            ("https://www.gnr.pt/contactos.aspx", "GNR"),
            ("https://www.gov.pt/contactos", "GovPT"),
            ("https://eportugal.gov.pt/contactos", "GovPT"),
        ]

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
            for url, agency in targets:
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200 and resp.text:
                        entries = self._parse_police_contacts(resp.text, agency, url)
                        discovered_entries.extend(entries)
                    else:
                        failed_count += 1
                except Exception as exc:
                    logger.debug("Failed to scrape target %s: %s", url, exc)
                    failed_count += 1

        scraped_count = len(discovered_entries)
        self.last_scraped_count = scraped_count
        self.last_failed_count = failed_count

        logger.info("Scraper execution finished. INFO: scraped %d esquadras, %d falharam.", scraped_count, failed_count)

        if discovered_entries:
            added = self._merge_into_database(discovered_entries)
            if added > 0:
                logger.info("Persisted %d newly discovered police stations to directory.", added)

        return {"scraped": scraped_count, "failed": failed_count}

    def _parse_police_contacts(self, html: str, agency: str, source_url: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            elements = soup.find_all(["div", "li", "p", "tr", "article"])
            for el in elements:
                txt = el.get_text(" ", strip=True)
                # Matches Portuguese landlines (21x, 22x, 23x, 24x, 25x, 26x, 27x, 28x, 29x)
                matches = re.findall(r"(?:(?:\+351\s*)?(?:2\d{1,2}|808)\s*\d{3}\s*\d{3,4})", txt)
                for raw_phone in matches:
                    clean = re.sub(r"\D", "", raw_phone)
                    clean_nat = clean[3:] if clean.startswith("351") else clean
                    if len(clean_nat) == 9:
                        first_line = txt.split("\n")[0][:90].strip()
                        results.append({
                            "number": clean_nat,
                            "name": f"{agency} - {first_line or 'Unidade Policial Oficial'}",
                            "category": "Polícia / Força de Segurança" if agency in ["PSP", "GNR"] else "Serviço Público Governamental",
                            "website": source_url,
                            "address": "Portugal",
                            "source": "official_scrape",
                            "confidence": "HIGH",
                            "is_official": True,
                        })
        except Exception as exc:
            logger.debug("Error parsing HTML for %s: %s", agency, exc)

        return results

    def _merge_into_database(self, new_entries: List[Dict[str, Any]]) -> int:
        if not self.output_file.exists():
            return 0

        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            existing_entries = data.get("entries", [])
            existing_numbers = {re.sub(r"\D", "", str(e.get("number", ""))) for e in existing_entries}

            added = 0
            for item in new_entries:
                num = re.sub(r"\D", "", str(item.get("number", "")))
                if num and num not in existing_numbers:
                    existing_entries.append(item)
                    existing_numbers.add(num)
                    added += 1

            if added > 0:
                data["entries"] = existing_entries
                with open(self.output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # Reload in-memory database and rebuild dynamic blocks
                paginas_amarelas_db.load()
                geographic_matcher.rebuild_dynamic_blocks()

            return added
        except Exception as exc:
            logger.error("Error saving updated directory database: %s", exc)
            return 0


# Global matcher instance
geographic_matcher = GeographicMatcher()
police_scraper = PoliceDirectoryScraper()
