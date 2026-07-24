import hmac
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, status

from www.backend.app.settings import get_settings


router = APIRouter(prefix="/tg", tags=["telegram"])

BOOTSTRAP_MESSAGE = (
    "Коммуналка «План Б» подключена. Перенос диалогового агента ещё идёт, "
    "поэтому оформление обращения здесь временно недоступно."
)


async def send_telegram_message(token: str, chat_id: int | str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()


def _message_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if isinstance(message, dict):
        return message
    callback = update.get("callback_query")
    if isinstance(callback, dict) and isinstance(callback.get("message"), dict):
        return callback["message"]
    return None


@router.post("/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    secret_header: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.telegram_enabled or not settings.telegram_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram_channel_disabled",
        )
    if not settings.telegram_webhook_secret or not secret_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    if not hmac.compare_digest(secret_header, settings.telegram_webhook_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    message = _message_from_update(update)
    chat = message.get("chat") if message else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if chat_id is not None:
        await send_telegram_message(
            settings.telegram_token,
            chat_id,
            BOOTSTRAP_MESSAGE,
        )

    return {
        "ok": True,
        "mode": "bootstrap",
        "update_id": update.get("update_id"),
    }
