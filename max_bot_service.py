#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MAX channel adapter for the common bot order pipeline.

This module intentionally keeps MAX transport concerns separate from the
business logic. User text is normalized into MessageHandlerService with
channel='maxchat', the same way Telegram text reaches the common pipeline.
"""

import argparse
import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional

try:
    from decouple import config
except ImportError:  # pragma: no cover - decouple is installed in production
    config = None

logger = logging.getLogger(__name__)

MAX_CHANNEL = "maxchat"
MAX_API_BASE_URL = "https://platform-api.max.ru"


class MaxBotError(Exception):
    """Base MAX adapter error."""


class MaxBotConfigError(MaxBotError):
    """MAX adapter is not configured."""


class MaxBotSecretError(MaxBotError):
    """Webhook secret validation failed."""


@dataclass
class MaxIncomingEvent:
    update_type: str
    text: str
    user_id: str
    chat_id: Optional[str]
    message_id: str
    metadata: Dict[str, Any]
    content_type: str = "text"
    audio_attachment: Optional[Dict[str, Any]] = None
    command_only: bool = False


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    if config is not None:
        return config(name, default=default)
    return os.getenv(name, default)


class MaxBotService:
    """Transport adapter for MAX bot events."""

    def __init__(
        self,
        token: Optional[str] = None,
        api_base_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        message_handler=None,
    ):
        self.token = token or _env("MAX_BOT_TOKEN") or _env("MAX_TOKEN")
        self.api_base_url = (api_base_url or _env("MAX_API_BASE_URL", MAX_API_BASE_URL)).rstrip("/")
        self.webhook_secret = webhook_secret if webhook_secret is not None else _env("MAX_BOT_WEBHOOK_SECRET")
        self.message_handler = message_handler
        self.bot_name = _env("MAX_BOT_DISPLAY_NAME", "Сигизмунд Лазоревич")

    def validate_secret(self, request_secret: Optional[str]) -> None:
        if self.webhook_secret and request_secret != self.webhook_secret:
            raise MaxBotSecretError("Invalid MAX webhook secret")

    async def process_update(
        self,
        update: Dict[str, Any],
        *,
        request_secret: Optional[str] = None,
        send_reply: bool = True,
        validate_webhook_secret: bool = False,
    ) -> Dict[str, Any]:
        """Process a single MAX update and optionally send the reply to MAX."""
        if validate_webhook_secret or request_secret is not None:
            self.validate_secret(request_secret)
        event = self.normalize_update(update)
        if not event:
            logger.info("MAX update ignored before pipeline: %s", self._safe_update_summary(update))
            return {"status": "ignored", "reason": "unsupported_or_empty_update"}

        if event.content_type == "audio":
            logger.info(
                "MAX audio message received: user_id=%s chat_id=%s message_id=%s audio=%s",
                event.user_id,
                event.chat_id,
                event.message_id,
                self._safe_attachment_metadata(event.audio_attachment or {}),
            )
            try:
                event = await self._transcribe_audio_event(event)
            except Exception as exc:
                logger.warning("MAX audio recognition failed: %s", exc, exc_info=True)
                response_text = "Аудио не распознано. Попробуйте записать сообщение короче или отправьте текстом."
                sent = None
                if send_reply:
                    sent = self._send_message_safe(response_text, user_id=event.user_id, chat_id=event.chat_id)
                return {
                    "status": "error",
                    "error": str(exc),
                    "response": response_text,
                    "session_id": None,
                    "sent": sent,
                    "content_type": "audio",
                }

        command_reply = None if self._extract_command(event.text) == "/start" else await self._command_reply(event)
        if command_reply is not None:
            sent = None
            if send_reply:
                sent = self._send_message_safe(command_reply, user_id=event.user_id, chat_id=event.chat_id)
            return {
                "status": "success",
                "response": command_reply,
                "session_id": None,
                "sent": sent,
                "command_only": True,
            }

        from message_handler_service import MessageHandlerService

        message_handler = self.message_handler or MessageHandlerService()
        result = await message_handler.handle_incoming_message(
            text=event.text,
            user_id=event.user_id,
            channel=MAX_CHANNEL,
            message_id=event.message_id,
            session_id=None,
            metadata=event.metadata,
            django_user_id=None,
        )

        response_text = result.get("response") or ""
        if response_text and send_reply:
            result["max_send_result"] = self._send_message_safe(
                self._repair_mojibake(response_text),
                user_id=event.user_id,
                chat_id=event.chat_id,
            )
        return result

    def normalize_update(self, update: Dict[str, Any]) -> Optional[MaxIncomingEvent]:
        """Convert MAX Update JSON to an internal incoming event."""
        if not isinstance(update, dict):
            return None

        update_type = str(update.get("update_type") or update.get("type") or "")
        if update_type == "message_created":
            return self._normalize_message_created(update)
        if update_type == "bot_started":
            return self._normalize_bot_started(update)
        return None

    def _normalize_message_created(self, update: Dict[str, Any]) -> Optional[MaxIncomingEvent]:
        message = update.get("message") or {}
        body = message.get("body") or update.get("body") or {}
        text = body.get("text") or message.get("text") or update.get("text") or ""
        text = str(text).strip()
        attachments = self._extract_attachments(update, message, body)
        audio_attachment = self._find_audio_attachment(attachments)
        if not text and not audio_attachment:
            return None

        sender = message.get("sender") or update.get("user") or {}
        recipient = message.get("recipient") or {}
        user_id = self._first_value(
            sender.get("user_id"),
            sender.get("id"),
            update.get("user_id"),
            update.get("userId"),
        )
        chat_id = self._first_value(
            update.get("chat_id"),
            update.get("chatId"),
            recipient.get("chat_id"),
            recipient.get("chatId"),
            message.get("chat_id"),
        )
        if not user_id and chat_id:
            user_id = chat_id
        if not user_id:
            return None

        message_id = self._first_value(
            body.get("mid"),
            body.get("message_id"),
            message.get("id"),
            message.get("message_id"),
            update.get("message_id"),
            f"max_{int(time.time() * 1000)}",
        )

        metadata = self._build_metadata(
            update=update,
            user=sender,
            update_type="message_created",
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
        )
        if audio_attachment:
            metadata.update({
                "content_type": "audio",
                "max_audio": self._safe_attachment_metadata(audio_attachment),
            })
        return MaxIncomingEvent(
            update_type="message_created",
            text=text,
            user_id=str(user_id),
            chat_id=str(chat_id) if chat_id is not None else None,
            message_id=str(message_id),
            metadata=metadata,
            content_type="audio" if audio_attachment else "text",
            audio_attachment=audio_attachment,
        )

    def _normalize_bot_started(self, update: Dict[str, Any]) -> Optional[MaxIncomingEvent]:
        user = update.get("user") or {}
        user_id = self._first_value(user.get("user_id"), user.get("id"), update.get("user_id"))
        chat_id = self._first_value(update.get("chat_id"), update.get("chatId"), user_id)
        if not user_id:
            return None
        message_id = f"max_bot_started_{user_id}_{update.get('timestamp') or int(time.time() * 1000)}"
        payload = update.get("payload")
        text = f"/start {payload}".strip() if payload else "/start"
        metadata = self._build_metadata(
            update=update,
            user=user,
            update_type="bot_started",
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
        )
        return MaxIncomingEvent(
            update_type="bot_started",
            text=text,
            user_id=str(user_id),
            chat_id=str(chat_id) if chat_id is not None else None,
            message_id=str(message_id),
            metadata=metadata,
            command_only=False,
        )

    def _build_metadata(
        self,
        *,
        update: Dict[str, Any],
        user: Dict[str, Any],
        update_type: str,
        chat_id: Optional[Any],
        user_id: Any,
        message_id: Any,
    ) -> Dict[str, Any]:
        display_name = self._first_value(
            user.get("username"),
            user.get("name"),
            user.get("first_name"),
            user.get("firstName"),
        )
        max_info = {
            "update_type": update_type,
            "timestamp": update.get("timestamp"),
            "chat_id": str(chat_id) if chat_id is not None else None,
            "user_id": str(user_id),
            "message_id": str(message_id),
            "username": user.get("username"),
            "name": user.get("name"),
            "first_name": user.get("first_name") or user.get("firstName"),
            "last_name": user.get("last_name") or user.get("lastName"),
        }
        return {
            "channel_adapter": "max_bot_service",
            "max_info": max_info,
            "username": user.get("username"),
            "first_name": user.get("first_name") or user.get("firstName") or display_name,
        }

    def _extract_attachments(self, *containers: Dict[str, Any]) -> list:
        attachments = []
        attachment_ids = set()
        visited_ids = set()

        def add_attachment(item: Any) -> None:
            if not isinstance(item, dict):
                return
            item_id = id(item)
            if item_id in attachment_ids:
                return
            attachment_ids.add(item_id)
            attachments.append(item)

        def visit(value: Any, depth: int = 0) -> None:
            if depth > 6:
                return
            if isinstance(value, list):
                for item in value:
                    visit(item, depth + 1)
                return
            if not isinstance(value, dict):
                return

            value_id = id(value)
            if value_id in visited_ids:
                return
            visited_ids.add(value_id)

            if self._looks_like_attachment(value):
                add_attachment(value)

            for key in ("attachments", "attachment"):
                raw = value.get(key)
                if isinstance(raw, list):
                    for item in raw:
                        add_attachment(item)
                        visit(item, depth + 1)
                elif isinstance(raw, dict):
                    add_attachment(raw)
                    visit(raw, depth + 1)

            for key, item in value.items():
                if key in {"attachments", "attachment"}:
                    continue
                if isinstance(item, (dict, list)):
                    visit(item, depth + 1)

        for container in containers:
            visit(container)
        return attachments

    def _looks_like_attachment(self, value: Dict[str, Any]) -> bool:
        payload = value.get("payload") if isinstance(value.get("payload"), dict) else {}
        type_text = " ".join(
            str(item or "").lower()
            for item in (
                value.get("type"),
                value.get("kind"),
                value.get("attachment_type"),
                payload.get("type"),
                payload.get("kind"),
                payload.get("media_type"),
            )
        )
        known_types = (
            "audio",
            "voice",
            "image",
            "video",
            "file",
            "sticker",
            "contact",
            "inline_keyboard",
            "keyboard",
            "share",
            "location",
        )
        if any(item in type_text for item in known_types):
            return True
        if not payload:
            return False
        if not any(key in value for key in ("type", "kind", "attachment_type")):
            return False
        payload_keys = {
            "url",
            "download_url",
            "downloadUrl",
            "file_url",
            "fileUrl",
            "token",
            "filename",
            "file_name",
            "mime_type",
            "mimeType",
        }
        return any(key in payload for key in payload_keys)

    def _find_audio_attachment(self, attachments: list) -> Optional[Dict[str, Any]]:
        for attachment in attachments:
            payload = attachment.get("payload") if isinstance(attachment.get("payload"), dict) else {}
            type_text = " ".join(
                str(value or "").lower()
                for value in (
                    attachment.get("type"),
                    attachment.get("kind"),
                    attachment.get("attachment_type"),
                    payload.get("type"),
                    payload.get("kind"),
                    payload.get("media_type"),
                )
            )
            mime_type = str(
                attachment.get("mime_type")
                or attachment.get("mimeType")
                or payload.get("mime_type")
                or payload.get("mimeType")
                or ""
            ).lower()
            file_name = str(
                attachment.get("file_name")
                or attachment.get("filename")
                or attachment.get("name")
                or payload.get("file_name")
                or payload.get("filename")
                or payload.get("name")
                or ""
            ).lower()
            if "audio" in type_text or "voice" in type_text:
                return attachment
            if mime_type.startswith("audio/"):
                return attachment
            if file_name.endswith((".ogg", ".opus", ".mp3", ".m4a", ".wav", ".oga", ".webm")):
                return attachment
        return None

    def _safe_attachment_metadata(self, attachment: Dict[str, Any]) -> Dict[str, Any]:
        def scrub(value: Any, depth: int = 0) -> Any:
            if depth > 3:
                return str(type(value).__name__)
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    key_lower = str(key).lower()
                    if any(marker in key_lower for marker in ("url", "token", "authorization", "content", "bytes", "data")):
                        result[key] = "[redacted]"
                    else:
                        result[key] = scrub(item, depth + 1)
                return result
            if isinstance(value, list):
                return [scrub(item, depth + 1) for item in value[:10]]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)

        return scrub(attachment)

    def _safe_update_summary(self, update: Any) -> Dict[str, Any]:
        if not isinstance(update, dict):
            return {"raw_type": type(update).__name__}

        message = update.get("message") if isinstance(update.get("message"), dict) else {}
        body = message.get("body") if isinstance(message.get("body"), dict) else {}
        if not body and isinstance(update.get("body"), dict):
            body = update.get("body") or {}
        sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
        if not sender and isinstance(update.get("user"), dict):
            sender = update.get("user") or {}
        text = body.get("text") or message.get("text") or update.get("text") or ""
        attachments = self._extract_attachments(update)
        return {
            "update_type": update.get("update_type") or update.get("type"),
            "keys": list(update.keys())[:30],
            "message_keys": list(message.keys())[:30],
            "body_keys": list(body.keys())[:30],
            "has_text": bool(str(text).strip()),
            "text_len": len(str(text or "")),
            "chat_id": self._first_value(
                update.get("chat_id"),
                update.get("chatId"),
                message.get("chat_id"),
                (message.get("recipient") or {}).get("chat_id") if isinstance(message.get("recipient"), dict) else None,
            ),
            "user_id": self._first_value(
                sender.get("user_id"),
                sender.get("id"),
                update.get("user_id"),
                update.get("userId"),
            ),
            "message_id": self._first_value(
                body.get("mid"),
                body.get("message_id"),
                message.get("id"),
                message.get("message_id"),
                update.get("message_id"),
            ),
            "attachment_count": len(attachments),
            "attachments": [self._safe_attachment_metadata(item) for item in attachments[:5]],
        }

    async def _transcribe_audio_event(self, event: MaxIncomingEvent) -> MaxIncomingEvent:
        if not event.audio_attachment:
            raise MaxBotError("MAX audio attachment is missing")

        audio_bytes, audio_metadata = await asyncio.to_thread(
            self._download_audio_attachment,
            event.audio_attachment,
            event.message_id,
        )
        from speech_to_text_service import SpeechToTextError, recognize_audio_bytes

        try:
            stt_result = await asyncio.to_thread(
                recognize_audio_bytes,
                audio_bytes,
                metadata={
                    **audio_metadata,
                    "channel": MAX_CHANNEL,
                    "media_kind": "audio",
                },
            )
        except SpeechToTextError as exc:
            raise MaxBotError(exc.message) from exc

        recognized_text = (stt_result.get("text") or "").strip()
        if not recognized_text:
            raise MaxBotError("MAX audio recognition returned empty text")

        metadata = dict(event.metadata or {})
        metadata.update({
            "content_type": "audio",
            "recognized_text": recognized_text,
            "stt": stt_result,
            "max_audio": {
                **metadata.get("max_audio", {}),
                **audio_metadata,
            },
        })
        return replace(event, text=recognized_text, metadata=metadata, content_type="text")

    def _download_audio_attachment(self, attachment: Dict[str, Any], message_id: str) -> tuple[bytes, Dict[str, Any]]:
        audio_attachment = attachment
        url = self._extract_first_url(audio_attachment)
        if not url and message_id:
            message = self.get_message(message_id)
            body = message.get("body") if isinstance(message, dict) else {}
            nested_attachments = self._extract_attachments(message, body or {})
            audio_attachment = self._find_audio_attachment(nested_attachments) or audio_attachment
            url = self._extract_first_url(audio_attachment)
        if not url:
            raise MaxBotError("MAX audio download URL is missing")

        if url.startswith("/"):
            url = f"{self.api_base_url}{url}"

        request = urllib.request.Request(url, headers={"Authorization": self.token or ""}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                limit = 20 * 1024 * 1024
                audio_bytes = response.read(limit + 1)
                content_type = response.headers.get("Content-Type")
        except urllib.error.HTTPError as exc:
            if exc.code not in {401, 403}:
                raise MaxBotError(f"MAX audio download HTTP {exc.code}") from exc
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=30) as response:
                limit = 20 * 1024 * 1024
                audio_bytes = response.read(limit + 1)
                content_type = response.headers.get("Content-Type")
        except urllib.error.URLError as exc:
            raise MaxBotError(f"MAX audio download failed: {exc}") from exc

        if len(audio_bytes) > 20 * 1024 * 1024:
            raise MaxBotError("MAX audio file is too large")

        parsed = urllib.parse.urlparse(url)
        file_name = os.path.basename(parsed.path)
        payload = audio_attachment.get("payload") if isinstance(audio_attachment.get("payload"), dict) else {}
        return audio_bytes, {
            "mime_type": content_type
            or audio_attachment.get("mime_type")
            or audio_attachment.get("mimeType")
            or payload.get("mime_type")
            or payload.get("mimeType"),
            "file_name": file_name
            or audio_attachment.get("file_name")
            or audio_attachment.get("filename")
            or payload.get("file_name")
            or payload.get("filename"),
            "size": len(audio_bytes),
        }

    def _extract_first_url(self, value: Any) -> Optional[str]:
        if isinstance(value, str):
            if value.startswith(("http://", "https://", "/")):
                return value
            return None
        if isinstance(value, dict):
            for key in ("download_url", "downloadUrl", "file_url", "fileUrl", "url", "link", "href"):
                url = self._extract_first_url(value.get(key))
                if url:
                    return url
            for item in value.values():
                url = self._extract_first_url(item)
                if url:
                    return url
        if isinstance(value, list):
            for item in value:
                url = self._extract_first_url(item)
                if url:
                    return url
        return None

    async def _command_reply(self, event: MaxIncomingEvent) -> Optional[str]:
        command = self._extract_command(event.text)
        if event.command_only and command != "/start":
            return None
        if command == "/start":
            name = event.metadata.get("first_name") or "пользователь"
            return self._welcome_text(name)
        if command == "/help":
            return self._help_text()
        if command == "/service":
            return (
                "Режим создания заявки активирован.\n\n"
                "Опишите проблему, и я определю необходимую услугу.\n"
                "Например: 'протекает кран' или 'нет электричества'\n\n"
                "Для отмены отправьте /cancel"
            )
        if command == "/address":
            return (
                "Режим проверки адреса активирован.\n\n"
                "Отправьте адрес для проверки (например: ул. Ленина, д. 5)\n\n"
                "Для отмены отправьте /cancel"
            )
        if command == "/cancel":
            return (
                "Операция отменена.\n\n"
                "Я готов к новым запросам. Используйте:\n"
                "/service - для создания заявки\n"
                "/address - для проверки адреса"
            )
        if command == "/streets":
            from asgiref.sync import sync_to_async

            return await sync_to_async(self._streets_text)()
        return None

    def _extract_command(self, text: str) -> Optional[str]:
        if not text:
            return None
        first = text.strip().split(maxsplit=1)[0].lower()
        if not first.startswith("/"):
            return None
        return first.split("@", 1)[0]

    def _welcome_text(self, name: str) -> str:
        return f"""Добрый день, {name}!

Я {self.bot_name} - AI-ассистент управляющей компании "Аспект".

Я могу помочь вам:
- Проверить адрес в зоне обслуживания УК
- Принять и зарегистрировать заявку на обслуживание
- Определить услугу по описанию проблемы

Просто отправьте мне сообщение с описанием проблемы или адрес для проверки.

Команды:
/help - справка
/streets - список улиц на обслуживании
/service - создать заявку по проблеме
/address - проверить адрес
"""

    def _help_text(self) -> str:
        return f"""Справка по боту {self.bot_name}

Основные функции:
- Описание проблемы -> Я определю услугу и помогу создать заявку
- Проверка адреса -> Уточню обслуживание УК "Аспект"
- Просмотр улиц -> Список всех улиц в зоне обслуживания

Примеры сообщений для заявок:
- "Протекает кран на кухне"
- "Нет света в квартире"
- "Забилась раковина в ванной"
- "Из потолка капает вода"

Команды:
/start - начало работы
/streets - список улиц на обслуживании
/service - режим создания заявки
/address - режим проверки адреса
/help - эта справка

Просто опишите проблему своими словами, а я определю нужную услугу!
"""

    def _streets_text(self) -> str:
        try:
            from kladr.models import KladrAddressObject

            streets_qs = (
                KladrAddressObject.objects.filter(type__level=5, building__isnull=False)
                .distinct()
                .order_by("name")[:50]
            )
            streets = [(obj.name, obj.type.short_name) for obj in streets_qs]
            if not streets:
                return "Улицы не найдены в базе данных"
            lines = ["Улицы в зоне обслуживания УК 'Аспект':", ""]
            for index, (name, type_name) in enumerate(streets, 1):
                lines.append(f"{index}. {type_name} {name}")
            lines.extend(["", f"Всего: {len(streets)} улиц", "", "Отправьте адрес для проверки (например: ул. Ленина, д. 5)"])
            text = "\n".join(lines)
            return text[:3950] + "...\n\n(и еще улицы)" if len(text) > 4000 else text
        except Exception as exc:
            logger.error("MAX streets command failed: %s", exc, exc_info=True)
            return "Ошибка при загрузке списка улиц"

    def send_message(
        self,
        text: str,
        *,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        notify: bool = True,
    ) -> Dict[str, Any]:
        if not text:
            return {"status": "ignored", "reason": "empty_text"}
        params: Dict[str, str] = {}
        if user_id:
            params["user_id"] = str(user_id)
        elif chat_id:
            params["chat_id"] = str(chat_id)
        else:
            raise MaxBotError("MAX recipient is missing")
        return self._api_request(
            "POST",
            "/messages",
            params=params,
            body={"text": text, "notify": notify},
        )

    def _send_message_safe(
        self,
        text: str,
        *,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            return self.send_message(text, user_id=user_id, chat_id=chat_id)
        except Exception as exc:
            logger.error("MAX reply send failed: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def get_me(self) -> Dict[str, Any]:
        return self._api_request("GET", "/me")

    def get_subscriptions(self) -> Dict[str, Any]:
        return self._api_request("GET", "/subscriptions")

    def get_message(self, message_id: str) -> Dict[str, Any]:
        encoded = urllib.parse.quote(str(message_id), safe="")
        return self._api_request("GET", f"/messages/{encoded}")

    def subscribe_webhook(self, url: str, *, secret: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "url": url,
            "update_types": ["message_created", "bot_started"],
        }
        if secret:
            body["secret"] = secret
        return self._api_request("POST", "/subscriptions", body=body)

    def get_updates(
        self,
        *,
        marker: Optional[str] = None,
        limit: int = 50,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        params = {
            "limit": str(limit),
            "timeout": str(timeout),
            "types": "message_created,bot_started",
        }
        if marker:
            params["marker"] = str(marker)
        return self._api_request("GET", "/updates", params=params, timeout=timeout + 10)

    def poll_forever(self) -> None:
        marker_file = _env("MAX_BOT_MARKER_FILE", "/tmp/komunal_dom_max_bot_marker.txt")
        marker = self._read_marker(marker_file)
        logger.info("MAX long polling started; marker=%s", marker)
        while True:
            try:
                data = self.get_updates(marker=marker)
                updates = data.get("updates") or []
                for update in updates:
                    asyncio.run(self.process_update(update, send_reply=True))
                marker = data.get("marker") or marker
                self._write_marker(marker_file, marker)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.error("MAX polling iteration failed: %s", exc, exc_info=True)
                time.sleep(5)

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        timeout: int = 20,
    ) -> Dict[str, Any]:
        if not self.token:
            raise MaxBotConfigError("MAX_BOT_TOKEN is not configured")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.api_base_url}{path}{query}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Authorization": self.token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {"success": True}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise MaxBotError(f"MAX API HTTP {exc.code}: {raw_error[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise MaxBotError(f"MAX API request failed: {exc}") from exc

    def _repair_mojibake(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        markers = ("Рџ", "Р—", "РЎ", "Рќ", "СЃ", "С‚", "СЋ", "СЏ")
        if not any(marker in text for marker in markers):
            return text
        try:
            repaired = text.encode("cp1251").decode("utf-8")
        except UnicodeError:
            return text
        return repaired if repaired else text

    def _read_marker(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as marker_file:
                marker = marker_file.read().strip()
                return marker or None
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Cannot read MAX marker file %s: %s", path, exc)
            return None

    def _write_marker(self, path: str, marker: Optional[str]) -> None:
        if marker is None:
            return
        try:
            with open(path, "w", encoding="utf-8") as marker_file:
                marker_file.write(str(marker))
        except OSError as exc:
            logger.warning("Cannot write MAX marker file %s: %s", path, exc)

    def _first_value(self, *values: Any) -> Optional[Any]:
        for value in values:
            if value is not None and value != "":
                return value
        return None


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "komunal_dom.settings")
    import django

    django.setup()


def main() -> None:
    parser = argparse.ArgumentParser(description="MAX bot channel adapter")
    parser.add_argument("--poll", action="store_true", help="Run MAX long polling loop")
    parser.add_argument("--me", action="store_true", help="Print MAX bot info")
    parser.add_argument("--subscriptions", action="store_true", help="Print MAX webhook subscriptions")
    parser.add_argument("--subscribe-webhook", help="Register webhook URL in MAX")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    setup_django()
    service = MaxBotService()

    if args.me:
        print(json.dumps(service.get_me(), ensure_ascii=False, indent=2))
    elif args.subscriptions:
        print(json.dumps(service.get_subscriptions(), ensure_ascii=False, indent=2))
    elif args.subscribe_webhook:
        print(
            json.dumps(
                service.subscribe_webhook(args.subscribe_webhook, secret=service.webhook_secret),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.poll:
        service.poll_forever()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
