import pytest
from app.engine.aggregator import aggregator
from app.engine.normalizer import normalize_phone_number
from app.engine.anacom import anacom_db
from app.engine.trusted_directory import lookup_trusted_directory
from app.engine.geographic_matcher import geographic_matcher
from app.models.schemas import (
    NormalizedNumberInfo,
    ScraperSourceResult,
    CrowdsourcedComment,
    CommercialEntityInfo,
    UserReportCreate,
)
from app.db.models import UserReport
from datetime import datetime, timezone

# Dataset of 60+ real known numbers across Portuguese districts, institutions, and categories
KNOWN_NUMBERS_DATASET = [
    # --- PSP: Lisboa ---
    {"number": "217657500", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Direção Nacional"},
    {"number": "217654242", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Cometlis Lisboa"},
    {"number": "218544000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Aeroporto Lisboa"},
    {"number": "213421212", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP 1ª Divisão Lisboa (Baixa)"},
    {"number": "213223400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP 2ª Divisão Lisboa (Rato)"},
    {"number": "217714600", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP 3ª Divisão Lisboa (Benfica)"},
    {"number": "218410800", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP 4ª Divisão Lisboa (Olivais)"},

    # --- PSP: Porto & Norte ---
    {"number": "222092000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Porto Comando"},
    {"number": "222092100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Porto Atendimento"},
    {"number": "226198100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Porto 1ª Divisão"},
    {"number": "225194600", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Porto 2ª Divisão"},
    {"number": "225083600", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Porto 3ª Divisão"},

    # --- PSP: Centro, Sul & Ilhas ---
    {"number": "239854400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Coimbra"},
    {"number": "253200420", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Braga"},
    {"number": "265534030", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Setúbal"},
    {"number": "289899990", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Faro"},
    {"number": "234371400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Aveiro"},
    {"number": "244859850", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Leiria"},
    {"number": "243309200", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Santarém"},
    {"number": "232483000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Viseu"},
    {"number": "258809610", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Viana do Castelo"},
    {"number": "259301600", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Vila Real"},
    {"number": "273300500", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Bragança"},
    {"number": "271200630", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Guarda"},
    {"number": "272330750", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Castelo Branco"},
    {"number": "245300300", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Portalegre"},
    {"number": "266760400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Évora"},
    {"number": "284313500", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Beja"},
    {"number": "291208400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Funchal"},
    {"number": "296205400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "PSP Ponta Delgada"},

    # --- GNR & PJ ---
    {"number": "213217000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "GNR Comando Geral"},
    {"number": "222076000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "GNR Comando Territorial Porto"},
    {"number": "253600400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "GNR Comando Territorial Braga"},
    {"number": "239794100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "GNR Comando Territorial Coimbra"},
    {"number": "289887600", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "GNR Comando Territorial Faro"},
    {"number": "211967000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Polícia Judiciária (PJ) Lisboa"},
    {"number": "225582000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Polícia Judiciária (PJ) Porto"},

    # --- Hospitais & Saúde ---
    {"number": "808242424", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "SNS 24"},
    {"number": "217805000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital de Santa Maria"},
    {"number": "225512100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital de São João"},
    {"number": "222077500", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital de Santo António"},
    {"number": "239400400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "CHUC Coimbra"},
    {"number": "212727100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital Garcia de Orta"},
    {"number": "253027000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital de Braga"},
    {"number": "265549000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital São Bernardo Setúbal"},
    {"number": "289891100", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Hospital de Faro"},
    {"number": "116006", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "APAV Apoio à Vítima"},
    {"number": "116111", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "SOS Criança"},

    # --- Serviços Públicos & Utilitários ---
    {"number": "218170000", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Câmara Municipal de Lisboa"},
    {"number": "222090400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Câmara Municipal do Porto"},
    {"number": "210471616", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "CTT Linha de Apoio"},
    {"number": "210545400", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Segurança Social Geral"},
    {"number": "300511499", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Segurança Social Linha Direta"},
    {"number": "217206707", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Autoridade Tributária / Finanças"},
    {"number": "211530530", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "EDP Comercial"},
    {"number": "808507500", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Entidade Oficial", "desc": "Galp Linha Oficial"},

    # --- Linhas Limpas & Reguladas ---
    {"number": "800123456", "expected_risk": "LOW", "expected_conf": "HIGH", "cat_contains": "Linha Verde", "desc": "Linha Verde 800"},
    {"number": "965551234", "expected_risk": "LOW", "expected_conf": "LOW", "cat_contains": "Contacto Móvel Pessoal", "desc": "Telemóvel Pessoal Limpo MEO"},
    {"number": "912345678", "expected_risk": "LOW", "expected_conf": "LOW", "cat_contains": "Contacto Móvel Pessoal", "desc": "Telemóvel Pessoal Limpo Vodafone"},
    {"number": "939876543", "expected_risk": "LOW", "expected_conf": "LOW", "cat_contains": "Contacto Móvel Pessoal", "desc": "Telemóvel Pessoal Limpo NOS"},
    {"number": "308123456", "expected_risk": "LOW", "expected_conf": "LOW", "cat_contains": "Nómada VoIP", "desc": "Número Nómada VoIP 308"},
]


@pytest.mark.parametrize("item", KNOWN_NUMBERS_DATASET, ids=lambda x: f"{x['desc']} ({x['number']})")
def test_known_numbers_classification(item):
    num = item["number"]
    norm = normalize_phone_number(num)
    anacom_info = anacom_db.lookup(norm.e164)
    trusted = lookup_trusted_directory(norm.e164, norm.national_format)
    geo_inference = geographic_matcher.match_institutional_range(norm.e164, norm.national_format)

    entity_info = None
    if trusted:
        entity_info = CommercialEntityInfo(
            is_commercial_entity=True,
            entity_name=trusted["name"],
            category=trusted.get("category", "Entidade Oficial"),
        )
    elif geo_inference:
        entity_info = CommercialEntityInfo(
            is_commercial_entity=True,
            entity_name=geo_inference["entity_hint"],
            category=geo_inference["institution_type"],
        )

    score, level, conf, matched_by, cat, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=anacom_info,
        sources=[],
        local_reports=[],
        commercial_entity=entity_info,
        is_trusted_directory=trusted is not None,
        geo_inference=geo_inference,
    )

    assert level == item["expected_risk"], f"Failed risk level for {item['desc']}: got {level}, expected {item['expected_risk']}"
    assert conf == item["expected_conf"], f"Failed confidence for {item['desc']}: got {conf}, expected {item['expected_conf']}"
    assert item["cat_contains"].lower() in cat.lower(), f"Failed category for {item['desc']}: got '{cat}', expected containing '{item['cat_contains']}'"


def test_geographic_prefix_inference_for_unlisted_station():
    """
    Test an unlisted police station number that is not explicitly in paginas_amarelas_pt.json,
    but falls into a known institutional PSP range (e.g. 217659999 in Lisbon or 253209999 in Braga).
    Must yield LOW risk (score 10), MEDIUM confidence, and geographic_prefix_inference.
    """
    unlisted_num = "217659999"  # Not explicitly in directory, but inside 21765 block
    norm = normalize_phone_number(unlisted_num)
    anacom_info = anacom_db.lookup(norm.e164)
    trusted = lookup_trusted_directory(norm.e164, norm.national_format)
    assert trusted is None, "Number should not be in static directory for this test"

    geo_inference = geographic_matcher.match_institutional_range(norm.e164, norm.national_format)
    assert geo_inference is not None
    assert geo_inference["confidence"] == "MEDIUM"
    assert "PSP" in geo_inference["institution_type"] or "Polícia" in geo_inference["institution_type"]

    score, level, conf, matched_by, cat, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=anacom_info,
        sources=[],
        local_reports=[],
        commercial_entity=None,
        is_trusted_directory=False,
        geo_inference=geo_inference,
    )

    assert level == "LOW"
    assert score == 10  # Low risk, but non-zero since it is an inference
    assert conf == "MEDIUM"
    assert matched_by == "geographic_prefix_inference"
    assert "Possível Força de Segurança" in cat or "PSP" in cat


UNLISTED_SUBURBAN_STATIONS = [
    {"number": "214349900", "desc": "PSP Amadora Reboleira"},
    {"number": "214849700", "desc": "PSP Cascais"},
    {"number": "219239800", "desc": "PSP Sintra Mem Martins"},
    {"number": "219329700", "desc": "PSP Odivelas"},
    {"number": "219839900", "desc": "PSP Loures"},
    {"number": "212729900", "desc": "PSP Almada Cacilhas"},
    {"number": "229389900", "desc": "PSP Matosinhos"},
    {"number": "224669900", "desc": "PSP Gondomar Rio Tinto"},
    {"number": "229419900", "desc": "PSP Maia Águas Santas"},
    {"number": "223779900", "desc": "PSP Gaia Soares dos Reis"},
    {"number": "217719999", "desc": "PSP Benfica Subunidade"},
    {"number": "218419999", "desc": "PSP Olivais Subunidade"},
]


@pytest.mark.parametrize("item", UNLISTED_SUBURBAN_STATIONS, ids=lambda x: f"{x['desc']} ({x['number']})")
def test_unlisted_suburban_stations_inferred_as_medium(item):
    num = item["number"]
    norm = normalize_phone_number(num)
    trusted = lookup_trusted_directory(norm.e164, norm.national_format)
    assert trusted is None, f"Expected {num} to NOT be in the exact trusted directory"

    geo_inference = geographic_matcher.match_institutional_range(norm.e164, norm.national_format)
    assert geo_inference is not None, f"Expected {num} to be inferred by dynamic geographic matcher"
    assert geo_inference["confidence"] == "MEDIUM"
    assert geo_inference["matched_by"] == "geographic_prefix_inference"

    score, level, conf, matched_by, cat, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=anacom_db.lookup(norm.e164),
        sources=[],
        local_reports=[],
        commercial_entity=None,
        is_trusted_directory=False,
        geo_inference=geo_inference,
    )

    assert level == "LOW"
    assert score == 10
    assert conf == "MEDIUM"
    assert matched_by == "geographic_prefix_inference"
    assert "Possível Força de Segurança" in cat or "Polícia" in cat or "Hospital" in cat or "PSP" in cat



def test_confirmed_fraud_overrides_anacom_and_yields_critical():
    """
    Test that a number with confirmed MBWay fraud reports gets CRITICAL risk and HIGH confidence.
    """
    fraud_num = "912999888"
    norm = normalize_phone_number(fraud_num)
    anacom_info = anacom_db.lookup(norm.e164)

    fake_report = UserReport(
        id=1,
        phone_e164=norm.e164,
        category="Burla / MBWay",
        caller_name="Burlão MBWay",
        comment="Tentativa de burla mbway no OLX, pediu para associar telemóvel ao MBWay",
        risk_rating=10,
        created_at=datetime.now(timezone.utc),
    )

    fake_scraper = ScraperSourceResult(
        source_name="Ligaram-me",
        success=True,
        spam_score=9.5,
        report_count=12,
        search_count=500,
        top_tags=["Burla", "MBWay"],
        comments=[
            CrowdsourcedComment(
                source="Ligaram-me",
                text="Atenção burla mbway a pedir códigos!",
                tag="Burla",
            )
        ],
    )

    score, level, conf, matched_by, cat, rec_pt, rec_en = aggregator._synthesize_risk(
        normalized=norm,
        anacom=anacom_info,
        sources=[fake_scraper],
        local_reports=[fake_report],
        commercial_entity=None,
        is_trusted_directory=False,
        geo_inference=None,
    )

    assert level == "CRITICAL"
    assert score >= 85
    assert conf == "HIGH"
    assert matched_by == "crowdsourced_only"
    assert "Burla" in cat
