from types import SimpleNamespace

from fastapi.testclient import TestClient

import tg.router as telegram_router
from www.backend.app.main import app


client = TestClient(app)


def test_disabled_telegram_webhook_returns_503(monkeypatch) -> None:
    monkeypatch.setattr(
        telegram_router,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=False,
            telegram_token="",
            telegram_webhook_secret="",
        ),
    )

    response = client.post("/tg/webhook", json={"update_id": 1})

    assert response.status_code == 503


def test_telegram_webhook_rejects_wrong_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        telegram_router,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_token="test-token",
            telegram_webhook_secret="right-secret",
        ),
    )

    response = client.post(
        "/tg/webhook",
        json={"update_id": 2},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )

    assert response.status_code == 403


def test_telegram_webhook_sends_bootstrap_reply(monkeypatch) -> None:
    sent: list[tuple[str, int | str, str]] = []

    async def fake_send(token: str, chat_id: int | str, text: str) -> None:
        sent.append((token, chat_id, text))

    monkeypatch.setattr(
        telegram_router,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_token="test-token",
            telegram_webhook_secret="right-secret",
        ),
    )
    monkeypatch.setattr(telegram_router, "send_telegram_message", fake_send)

    response = client.post(
        "/tg/webhook",
        json={"update_id": 3, "message": {"chat": {"id": 42}, "text": "Привет"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "right-secret"},
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "bootstrap"
    assert sent == [("test-token", 42, telegram_router.BOOTSTRAP_MESSAGE)]
