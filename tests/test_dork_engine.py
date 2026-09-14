import os
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.engine.scrapers.dork_engine import detect_institutional_signal, SearchDorkEngine
from app.core.observability import record_dork_debug
from app.models.schemas import CommercialEntityInfo, NormalizedNumberInfo
from app.engine.aggregator import PhoneIntelligenceAggregator
from app.engine.normalizer import normalize_phone_number


def test_detect_institutional_signal_psp():
    # 1. PSP station on parish council site
    snippet = "Contactos: 214 849 700. cascais.lisboa@psp.pt"
    title = "Polícia Segurança Pública - Cascais - Junta de Freguesia"
    url = "https://jf-cascaisestoril.pt/contactos"
    sig = detect_institutional_signal(snippet, title, url)
    assert sig is not None
    assert sig["entity_type"] == "PSP"
    assert sig["is_police"] is True
    assert "Polícia Segurança Pública" in sig["entity_name"]


def test_detect_institutional_signal_gnr():
    # 2. GNR territorial post
    snippet = "Posto Territorial da Guarda Nacional Republicana. Linha de apoio: 219 234 567."
    title = "GNR Posto Territorial de Sintra"
    url = "https://noticiasdesintra.pt/gnr"
    sig = detect_institutional_signal(snippet, title, url)
    assert sig is not None
    assert sig["entity_type"] == "GNR"
    assert sig["is_police"] is True


def test_detect_institutional_signal_esquadra_and_divisao():
    # 3. Esquadra / Divisão policial
    snippet = "Comando Metropolitano de Lisboa DIVISÃO POLICIAL DA AMADORA ... Divisão 21 434 99 00"
    title = "Lista de Esquadras PSP"
    url = "https://www.scribd.com/doc/123/esquadras"
    sig = detect_institutional_signal(snippet, title, url)
    assert sig is not None
    assert sig["is_police"] is True
    assert sig["entity_type"] == "PSP"


def test_detect_institutional_signal_hospital():
    # 4. Hospital
    snippet = "Centro Hospitalar de Lisboa Central. Contacto geral de urgências."
    title = "Hospital de São José"
    url = "https://chlc.min-saude.pt"
    sig = detect_institutional_signal(snippet, title, url)
    assert sig is not None
    assert sig["entity_type"] == "HOSPITAL"
    assert sig["is_police"] is False


def test_detect_institutional_signal_non_institutional():
    # 5. Regular commercial business
    snippet = "Temos as melhores pizzas e massas artesanais para entrega em Lisboa."
    title = "Pizzaria Bella Napoli Lisboa"
    url = "https://bellanapoli.pt"
    sig = detect_institutional_signal(snippet, title, url)
    assert sig is None


def test_record_dork_debug_file_creation(tmp_path):
    phone = "+351214849700"
    queries = ['"214849700" PSP', '"214849700" esquadra']
    raw_results = [
        {"title": "Polícia Cascais", "snippet": "Contactos: 214 849 700", "href": "https://jf-cascais.pt"}
    ]
    detected_signals = [{"entity_type": "PSP", "entity_name": "Polícia Cascais"}]

    filepath = record_dork_debug(
        phone_e164=phone,
        queries=queries,
        raw_results=raw_results,
        detected_signals=detected_signals,
        matched=True,
        matched_by="dork_consensus",
        consensus_sources=["jf-cascais.pt", "rr.sapo.pt"],
    )

    assert filepath != ""
    assert os.path.exists(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["phone_e164"] == phone
    assert data["matched"] is True
    assert data["matched_by"] == "dork_consensus"
    assert data["consensus_sources_count"] == 2
    assert len(data["queries"]) == 2


def test_aggregator_dork_consensus_risk_synthesis():
    aggregator = PhoneIntelligenceAggregator()
    normalized = normalize_phone_number("214849700")

    # Simulate 2 independent agreeing sources -> dork_consensus
    dork_info = CommercialEntityInfo(
        is_commercial_entity=True,
        entity_name="Divisão Policial de Cascais",
        category="Polícia / Segurança Pública",
        website="https://jf-cascais.pt",
        confidence="HIGH",
        matched_by="dork_consensus",
        consensus_count=2,
    )

    risk_score, risk_level, confidence, matched_by, cat, rec_pt, _ = aggregator._synthesize_risk(
        normalized=normalized,
        anacom=None,
        sources=[],
        local_reports=[],
        commercial_entity=dork_info,
        is_trusted_directory=False,
        geo_inference=None,
        dork_info=dork_info,
    )

    assert risk_score == 0
    assert risk_level == "LOW"
    assert confidence == "HIGH"
    assert matched_by == "dork_consensus"
    assert "Divisão Policial de Cascais" in cat


def test_aggregator_dork_inference_risk_synthesis():
    aggregator = PhoneIntelligenceAggregator()
    normalized = normalize_phone_number("214849700")

    # Simulate 1 source -> dork_inference
    dork_info = CommercialEntityInfo(
        is_commercial_entity=True,
        entity_name="Esquadra da PSP de Odivelas",
        category="Polícia / Segurança Pública",
        website="https://odivelas.pt",
        confidence="MEDIUM",
        matched_by="dork_inference",
        consensus_count=1,
    )


    risk_score, risk_level, confidence, matched_by, cat, rec_pt, _ = aggregator._synthesize_risk(
        normalized=normalized,
        anacom=None,
        sources=[],
        local_reports=[],
        commercial_entity=dork_info,
        is_trusted_directory=False,
        geo_inference=None,
        dork_info=dork_info,
    )

    assert risk_score == 10
    assert risk_level == "LOW"
    assert confidence == "MEDIUM"
    assert matched_by == "dork_inference"
