import pytest
from app.engine.normalizer import normalize_phone_number


def test_normalize_portuguese_mobile():
    res = normalize_phone_number("912345678")
    assert res.is_valid is True
    assert res.e164 == "+351912345678"
    assert res.country_code == 351
    assert res.region_code == "PT"
    assert res.line_type == "MOBILE"
    assert "912 345 678" in res.national_format


def test_normalize_portuguese_fixed():
    res = normalize_phone_number("213456789")
    assert res.is_valid is True
    assert res.e164 == "+351213456789"
    assert res.country_code == 351
    assert res.region_code == "PT"
    assert res.line_type == "FIXED_LINE"


def test_normalize_portuguese_toll_free():
    res = normalize_phone_number("800200115")
    assert res.is_valid is True
    assert res.e164 == "+351800200115"
    assert res.line_type == "TOLL_FREE"


def test_normalize_international_spain():
    res = normalize_phone_number("+34911234567")
    assert res.is_valid is True
    assert res.country_code == 34
    assert res.region_code == "ES"


def test_normalize_invalid_number():
    res = normalize_phone_number("123")
    assert res.is_valid is False
