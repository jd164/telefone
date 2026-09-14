import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

PAGINAS_AMARELAS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "paginas_amarelas_pt.json"


class PaginasAmarelasDatabase:
    """
    High-performance indexed registry of Portuguese Public Services, Police (PSP/GNR),
    Emergency, Hospitals, Municipalities, Courts, and Páginas Amarelas Business directory entries.
    Supports distinguishing between curated seed data and dynamic official scrape data.
    """

    def __init__(self, data_file: Path = PAGINAS_AMARELAS_FILE):
        self.data_file = data_file
        self._entries_by_number: Dict[str, Dict[str, Any]] = {}
        self._raw_entries: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if not self.data_file.exists():
            logger.warning("Páginas Amarelas seed file not found at %s", self.data_file)
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                entries: List[Dict[str, Any]] = data.get("entries", [])
                self._raw_entries = entries
                self._entries_by_number.clear()

                for item in entries:
                    raw_num = str(item.get("number", ""))
                    clean_digits = re.sub(r"\D", "", raw_num)
                    if clean_digits:
                        # Ensure default source metadata
                        if "source" not in item:
                            item["source"] = "curated"
                        self._entries_by_number[clean_digits] = item
                        if clean_digits.startswith("351"):
                            self._entries_by_number[clean_digits[3:]] = item

            logger.info("Loaded %d Páginas Amarelas & Official Directory entries.", len(self._entries_by_number))
        except Exception as exc:
            logger.error("Failed to load Páginas Amarelas database: %s", exc)

    def lookup(self, e164: str, national_digits: str) -> Optional[Dict[str, Any]]:
        clean_e164 = re.sub(r"\D", "", e164)
        clean_nat = clean_e164[3:] if clean_e164.startswith("351") else clean_e164
        clean_input = re.sub(r"\D", "", national_digits)

        if clean_nat in self._entries_by_number:
            return self._entries_by_number[clean_nat]

        if clean_input in self._entries_by_number:
            return self._entries_by_number[clean_input]

        if clean_e164 in self._entries_by_number:
            return self._entries_by_number[clean_e164]

        return None

    @property
    def total_entries(self) -> int:
        return len(self._raw_entries)

    def get_all_confirmed_numbers(self) -> List[Dict[str, Any]]:
        """Returns all confirmed institutional and commercial directory entries."""
        return list(self._raw_entries)

    def get_directory_stats(self) -> Dict[str, Any]:
        """Provides breakdown of entries by origin (curated vs official_scrape) and agency type."""
        curated_count = 0
        scraped_count = 0
        by_agency = {
            "PSP": 0,
            "GNR": 0,
            "PJ": 0,
            "Hospitais / Saúde": 0,
            "Câmaras / Autarquias": 0,
            "Serviços Públicos / Estado": 0,
            "Empresas & Outros": 0,
        }

        for item in self._raw_entries:
            src = item.get("source", "curated")
            if src == "official_scrape":
                scraped_count += 1
            else:
                curated_count += 1

            name = item.get("name", "")
            cat = item.get("category", "")
            combined = f"{name} {cat}".lower()

            if "psp" in combined or "polícia de segurança pública" in combined:
                by_agency["PSP"] += 1
            elif "gnr" in combined or "guarda nacional republicana" in combined:
                by_agency["GNR"] += 1
            elif "polícia judiciária" in combined or "pj" in combined:
                by_agency["PJ"] += 1
            elif any(k in combined for k in ["hospital", "saúde", "sns", "chuc", "uls", "médic"]):
                by_agency["Hospitais / Saúde"] += 1
            elif any(k in combined for k in ["câmara municipal", "autarquia", "município"]):
                by_agency["Câmaras / Autarquias"] += 1
            elif any(k in combined for k in ["segurança social", "finanças", "ctt", "autoridade tributária", "edp", "serviço público"]):
                by_agency["Serviços Públicos / Estado"] += 1
            else:
                by_agency["Empresas & Outros"] += 1

        return {
            "total_entries": len(self._raw_entries),
            "unique_numbers_indexed": len(self._entries_by_number),
            "curated_count": curated_count,
            "scraped_count": scraped_count,
            "by_agency": by_agency,
        }


# Global singleton
paginas_amarelas_db = PaginasAmarelasDatabase()


def lookup_trusted_directory(e164: str, national_digits: str) -> Optional[Dict[str, Any]]:
    return paginas_amarelas_db.lookup(e164, national_digits)
