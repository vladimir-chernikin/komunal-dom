from fastapi.testclient import TestClient

from www.backend.app.main import app


client = TestClient(app)


def test_auth_stub_is_the_home_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Вход в Коммуналку" in response.text
    assert "<form" in response.text
    assert 'action="' not in response.text


def test_health_is_available() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_business_api_cannot_accept_asterisk_traffic() -> None:
    response = client.post("/chat/api/external/", json={"text": "test"})

    assert response.status_code == 503
    assert response.json()["detail"]["ready_for_traffic"] is False
