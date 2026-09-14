import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("pipeline.observability")


class PipelineTelemetry:
    """
    Structured observability tracker for phone intelligence pipeline executions.
    Logs structured JSON metrics per query and maintains aggregated layer metrics.
    """

    _layer_stats: Dict[str, Dict[str, int]] = {
        "anacom": {"hit": 0, "miss": 0},
        "trusted_directory": {"hit": 0, "miss": 0},
        "geographic_matcher": {"hit": 0, "miss": 0},
        "tellows": {"ok": 0, "fail": 0, "miss": 0},
        "quem_liga": {"ok": 0, "fail": 0, "miss": 0},
        "should_i_answer": {"ok": 0, "fail": 0, "miss": 0},
        "unknown_phone": {"ok": 0, "fail": 0, "miss": 0},
        "dork_engine": {"hit": 0, "miss": 0, "fail": 0, "cached_hit": 0},
    }

    def __init__(self, phone_e164: str):
        self.phone_e164 = phone_e164
        self.start_time = time.perf_counter()
        self.layers: Dict[str, str] = {}

    def record_layer(self, layer_name: str, status: str):
        """
        Record outcome of a layer (e.g., 'hit', 'miss', 'ok', 'fail', 'cached_hit').
        """
        self.layers[layer_name] = status
        # Update global aggregated metrics
        if layer_name in self._layer_stats:
            self._layer_stats[layer_name][status] = self._layer_stats[layer_name].get(status, 0) + 1

    def finish(
        self,
        risk_score: int,
        risk_level: str,
        confidence: str,
        matched_by: str,
        cached: bool = False,
    ) -> Dict[str, Any]:
        duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "pipeline_lookup",
            "phone": self.phone_e164,
            "cached": cached,
            "duration_ms": duration_ms,
            "layers": self.layers,
            "result": {
                "risk_score": risk_score,
                "risk_level": risk_level,
                "confidence": confidence,
                "matched_by": matched_by,
            },
        }

        # Emit structured JSON log to stdout/logger
        logger.info(json.dumps(payload, ensure_ascii=False))
        return payload

    @classmethod
    def get_aggregated_stats(cls) -> Dict[str, Any]:
        return cls._layer_stats


def record_dork_debug(
    phone_e164: str,
    queries: list,
    raw_results: list,
    detected_signals: list,
    matched: bool,
    matched_by: Optional[str] = None,
    consensus_sources: Optional[list] = None,
) -> str:
    """
    Persists raw OSINT dork search queries, returned snippets, and parser detections
    to data/dork_debug/<clean_phone>.json for quick inspection and troubleshooting.
    """
    try:
        import os
        from pathlib import Path
        clean_num = "".join(c for c in phone_e164 if c.isdigit())
        debug_dir = Path(__file__).resolve().parent.parent.parent / "data" / "dork_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_file = debug_dir / f"{clean_num}.json"

        debug_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phone_e164": phone_e164,
            "matched": matched,
            "matched_by": matched_by,
            "consensus_sources_count": len(consensus_sources or []),
            "consensus_sources": consensus_sources or [],
            "queries": queries,
            "detected_signals": detected_signals,
            "raw_results_count": len(raw_results),
            "raw_results": raw_results,
        }

        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(debug_payload, f, ensure_ascii=False, indent=2)

        logger.info("Saved dork debug record to %s (found %d raw results)", debug_file, len(raw_results))
        return str(debug_file)
    except Exception as exc:
        logger.warning("Failed to record dork debug for %s: %s", phone_e164, exc)
        return ""

