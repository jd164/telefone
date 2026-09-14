import pytest
from app.engine.aggregator import aggregator
from app.models.schemas import (
    NormalizedNumberInfo,
    AnacomInfo,
    ScraperSourceResult,
    CommercialEntityInfo,
    CrowdsourcedComment,
)


def test_synthesize_risk_clean_number():
    norm = NormalizedNumberInfo(
        raw_input="912345678",
        e164="+351912345678",
        national_format="912 345 678",
        international_format="+351 912 345 678",
        country_code=351,
        country_name="Portugal",
        region_code="PT",
        line_type="MOBILE",
        is_valid=True,
        is_possible=True,
    )
    score, level, conf, matched_by, category, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=None,
        sources=[],
        local_reports=[],
        commercial_entity=None,
    )
    assert level == "LOW"
    assert score < 30
    assert "Não Identificado" in category or "Pessoal" in category


def test_synthesize_risk_fraud_mbway_spike():
    norm = NormalizedNumberInfo(
        raw_input="912345678",
        e164="+351912345678",
        national_format="912 345 678",
        international_format="+351 912 345 678",
        country_code=351,
        country_name="Portugal",
        region_code="PT",
        line_type="MOBILE",
        is_valid=True,
        is_possible=True,
    )
    fake_source = ScraperSourceResult(
        source_name="TestScraper",
        success=True,
        spam_score=9.5,
        top_tags=["Burla MBWay"],
        comments=[
            CrowdsourcedComment(
                source="TestScraper",
                text="Tentou burla de MBWay ao dizer que comprava artigo no OLX e pediu código no multibanco.",
            )
        ],
    )
    score, level, conf, matched_by, category, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=None,
        sources=[fake_source],
        local_reports=[],
        commercial_entity=None,
    )
    assert level == "CRITICAL"
    assert score >= 80
    assert "MBWay" in category
    assert "Bloquear imediatamente" in rec_pt


def test_synthesize_risk_verified_commercial_entity():
    norm = NormalizedNumberInfo(
        raw_input="210000000",
        e164="+351210000000",
        national_format="210 000 000",
        international_format="+351 210 000 000",
        country_code=351,
        country_name="Portugal",
        region_code="PT",
        line_type="FIXED_LINE",
        is_valid=True,
        is_possible=True,
    )
    biz = CommercialEntityInfo(
        is_commercial_entity=True,
        entity_name="Hospital de Santa Maria",
        category="Hospital",
        website="https://www.chln.min-saude.pt",
    )
    score, level, conf, matched_by, category, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=None,
        sources=[],
        local_reports=[],
        commercial_entity=biz,
    )
    assert level == "LOW"
    assert score <= 20
    assert "Empresa" in category or "Comercial" in category or "Entidade Oficial" in category


def test_trusted_directory_sns24():
    from app.engine.trusted_directory import lookup_trusted_directory
    data = lookup_trusted_directory("+351808242424", "808 24 24 24")
    assert data is not None
    assert "SNS 24" in data["name"]


def test_clean_unrated_personal_number():
    norm = NormalizedNumberInfo(
        raw_input="965551234",
        e164="+351965551234",
        national_format="965 551 234",
        international_format="+351 965 551 234",
        country_code=351,
        country_name="Portugal",
        region_code="PT",
        line_type="MOBILE",
        is_valid=True,
        is_possible=True,
    )
    score, level, conf, matched_by, category, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=None,
        sources=[],
        local_reports=[],
        commercial_entity=None,
    )
    assert level == "LOW"
    assert score <= 10
    assert "Sem Queixas" in category
