import pytest
from app.engine.anacom import anacom_db


def test_anacom_database_loaded():
    assert anacom_db.total_prefixes > 20


def test_anacom_lookup_lisbon_fixed():
    info = anacom_db.lookup("+351213456789")
    assert info is not None
    assert info.matched_prefix == "21"
    assert info.service_type == "Geographic Fixed"
    assert "Lisboa" in info.geographic_area
    assert info.is_voip is False


def test_anacom_lookup_vodafone_mobile():
    info = anacom_db.lookup("+351912345678")
    assert info is not None
    assert info.matched_prefix == "91"
    assert info.service_type == "Mobile"
    assert "Vodafone" in info.primary_operators[0]


def test_anacom_lookup_nomadic_voip():
    info = anacom_db.lookup("+351308123456")
    assert info is not None
    assert info.matched_prefix == "308"
    assert info.service_type == "Nomadic VoIP"
    assert info.is_voip is True
    assert info.base_risk_modifier > 0


def test_anacom_lookup_toll_free():
    info = anacom_db.lookup("+351800200115")
    assert info is not None
    assert info.matched_prefix == "800"
    assert info.service_type == "Toll-Free"
    assert info.base_risk_modifier < 0  # Reduces risk


def test_anacom_lookup_premium_mass_calling():
    info = anacom_db.lookup("+351760100200")
    assert info is not None
    assert info.matched_prefix == "760"
    assert info.service_type == "Premium Rate Mass Calling"
    assert info.base_risk_modifier >= 30


def test_anacom_lookup_international_number():
    info = anacom_db.lookup("+34911234567")
    assert info is None
