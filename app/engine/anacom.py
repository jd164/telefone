import json
import logging
from typing import Optional, Dict, Any, List
from app.core.config import settings
from app.models.schemas import AnacomInfo

logger = logging.getLogger(__name__)


class AnacomPnnDatabase:
    """
    In-memory prefix tree and matcher for ANACOM Plano Nacional de Numeração (PNN).
    Provides microsecond-fast longest-prefix lookup for Portuguese telecom ranges.
    """

    def __init__(self, data_path=settings.ANACOM_DATA_FILE):
        self.data_path = data_path
        self.prefix_rules: List[Dict[str, Any]] = []
        self._prefix_map: Dict[str, Dict[str, Any]] = {}
        self.load_data()

    def load_data(self):
        try:
            if not self.data_path.exists():
                logger.warning("ANACOM seed data file not found at %s", self.data_path)
                return

            with open(self.data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.prefix_rules = data.get("prefix_rules", [])

            # Index by prefix for quick longest-prefix matching
            for rule in self.prefix_rules:
                prefix = str(rule.get("prefix", ""))
                if prefix:
                    self._prefix_map[prefix] = rule

            logger.info("Loaded %d ANACOM prefix rules successfully.", len(self._prefix_map))
        except Exception as exc:
            logger.error("Error loading ANACOM seed data: %s", exc)

    def lookup(self, e164_number: str) -> Optional[AnacomInfo]:
        """
        Looks up a phone number against the ANACOM PNN prefix table.
        Expects E.164 string like '+351912345678' or '+351213456789'.
        Returns AnacomInfo if it is a Portuguese number (+351), otherwise None.
        """
        if not e164_number.startswith("+351"):
            return None

        # Extract national number without '+351'
        national_digits = e164_number[4:]

        # Find longest matching prefix
        matched_rule: Optional[Dict[str, Any]] = None
        matched_prefix: Optional[str] = None

        # Check lengths from longest prefix down to 2 digits
        for length in range(min(len(national_digits), 6), 1, -1):
            sub = national_digits[:length]
            if sub in self._prefix_map:
                matched_rule = self._prefix_map[sub]
                matched_prefix = sub
                break

        if not matched_rule:
            return None

        return AnacomInfo(
            matched_prefix=matched_prefix,
            service_type=matched_rule.get("service_type"),
            designation=matched_rule.get("designation"),
            geographic_area=matched_rule.get("geographic_area"),
            primary_operators=matched_rule.get("primary_operators", []),
            technology=matched_rule.get("technology"),
            is_voip=matched_rule.get("is_voip", False),
            base_risk_modifier=matched_rule.get("base_risk_modifier", 0),
            notes=matched_rule.get("notes"),
        )

    @property
    def total_prefixes(self) -> int:
        return len(self._prefix_map)


# Global singleton
anacom_db = AnacomPnnDatabase()
