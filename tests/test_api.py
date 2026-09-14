import pytest
from starlette.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["anacom_prefixes_loaded"] >= 50
    assert data["database_connected"] is True


def test_anacom_prefixes_endpoint(client):
    res = client.get("/api/v1/anacom/prefixes")
    assert res.status_code == 200
    data = res.json()
    assert data["authority"] == "ANACOM (Portugal)"
    assert len(data["rules"]) > 0


def test_lookup_endpoint(client):
    res = client.get("/api/v1/lookup?number=912345678")
    assert res.status_code == 200
    data = res.json()
    assert data["normalized"]["e164"] == "+351912345678"
    assert data["anacom"]["matched_prefix"] == "91"
    assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert 0 <= data["risk_score"] <= 100


def test_report_and_history_endpoint(client):
    # 1. Submit report
    report_payload = {
        "phone_number": "912345678",
        "category": "Burla / MBWay",
        "caller_name": "Falso Comprador MBWay",
        "comment": "Tentativa de burla ao solicitar ativação MBWay numa caixa multibanco.",
        "risk_rating": 10,
    }
    post_res = client.post("/api/v1/report", json=report_payload)
    assert post_res.status_code == 200
    rep_data = post_res.json()
    assert rep_data["phone_e164"] == "+351912345678"
    assert rep_data["category"] == "Burla / MBWay"

    # 2. Check reports endpoint
    get_rep = client.get("/api/v1/reports/912345678")
    assert get_rep.status_code == 200
    assert len(get_rep.json()) >= 1

    # 3. Check history endpoint
    hist_res = client.get("/api/v1/history")
    assert hist_res.status_code == 200


def test_dashboard_ui_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Phone Number Intelligence Aggregator" in res.text
