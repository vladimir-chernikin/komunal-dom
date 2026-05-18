#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MAX notifier for new work orders.

This service is separate from max_bot_service.py:
- max_bot_service.py is a resident-facing message transport;
- max_notification_service.py is an internal service notification sender.
"""

import argparse
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

try:
    from decouple import config
except ImportError:  # pragma: no cover
    config = None

logger = logging.getLogger(__name__)

MAX_API_BASE_URL = "https://platform-api.max.ru"
DEFAULT_TARGET_FILE = "/var/www/komunal-dom_ru/runtime/max_notifier_target.json"
DEFAULT_PENDING_FILE = "/var/www/komunal-dom_ru/runtime/max_notifier_pending.jsonl"
DEFAULT_ASTERISK_CALL_URL = "http://84.54.30.197:9000/call"
DEFAULT_ASTERISK_CALL_TIMEOUT = 45


class MaxNotificationError(Exception):
    """MAX notification error."""


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    if config is not None:
        return config(name, default=default)
    return os.getenv(name, default)


class MaxNotificationService:
    def __init__(
        self,
        token: Optional[str] = None,
        api_base_url: Optional[str] = None,
        target_chat_id: Optional[str] = None,
        target_user_id: Optional[str] = None,
        extra_chat_ids: Optional[str] = None,
        extra_user_ids: Optional[str] = None,
        target_file: Optional[str] = None,
        pending_file: Optional[str] = None,
        asterisk_call_url: Optional[str] = None,
        asterisk_call_token: Optional[str] = None,
    ):
        self.token = token or _env("MAX_NOTIFIER_BOT_TOKEN")
        self.api_base_url = (api_base_url or _env("MAX_API_BASE_URL", MAX_API_BASE_URL)).rstrip("/")
        self.target_chat_id = target_chat_id or _env("MAX_NOTIFIER_CHAT_ID")
        self.target_user_id = target_user_id or _env("MAX_NOTIFIER_USER_ID")
        self.extra_chat_ids = self._split_ids(
            extra_chat_ids or _env("MAX_NOTIFIER_EXTRA_CHAT_IDS") or _env("MAX_NOTIFIER_CHAT_IDS")
        )
        self.extra_user_ids = self._split_ids(
            extra_user_ids or _env("MAX_NOTIFIER_EXTRA_USER_IDS") or _env("MAX_NOTIFIER_USER_IDS")
        )
        self.target_file = target_file or _env("MAX_NOTIFIER_TARGET_FILE", DEFAULT_TARGET_FILE)
        self.pending_file = pending_file or _env("MAX_NOTIFIER_PENDING_FILE", DEFAULT_PENDING_FILE)
        self.asterisk_call_url = (
            asterisk_call_url
            or _env("ASTERISK_OUTBOUND_CALL_URL")
            or _env("ASTERISK_CALL_URL")
            or DEFAULT_ASTERISK_CALL_URL
        )
        self.asterisk_call_token = (
            asterisk_call_token
            or _env("ASTERISK_OUTBOUND_CALL_TOKEN")
            or _env("ASTERISK_CONTROL_TOKEN")
            or _env("ASTERISK_API_TOKEN")
            or _env("EXTERNAL_API_TOKEN")
        )

    def notify_new_work_order(self, work_order) -> Dict[str, Any]:
        return self.send_notification(self.format_new_work_order_message(work_order))

    def notify_new_work_order_by_id(self, work_order_id: int) -> Dict[str, Any]:
        from work_orders.models import WorkOrder

        return self.notify_new_work_order(WorkOrder.objects.get(pk=work_order_id))

    def format_new_work_order_message(self, work_order) -> str:
        from django.utils import timezone

        created_at = work_order.created_at or timezone.now()
        request_text = (work_order.original_request_text or "").strip()
        return (
            f"[{timezone.localtime(created_at).strftime('%d.%m.%Y %H:%M:%S')}]:  "
            f"Ваиртуальная АДС: Создана новая заявка с Номером {work_order.work_order_no}\n"
            "Текст заявки:\n"
            f"{request_text}"
        )

    def send_notification(self, text: str) -> Dict[str, Any]:
        targets = self.get_targets()
        if not targets:
            self.enqueue_pending(text, reason="target_missing")
            logger.warning("MAX notifier target is not configured; notification queued")
            return {"status": "queued", "reason": "target_missing"}

        sent = []
        failed = []
        for target in targets:
            try:
                result = self._send_text(text, target)
                sent.append({"target": target, "result": result})
            except Exception as exc:
                failed.append({"target": target, "reason": str(exc)})
                self.enqueue_pending(text, reason=str(exc), target=target)
                logger.error("MAX new order notification failed and was queued: %s", exc, exc_info=True)

        if sent and not failed:
            logger.info("MAX new order notification sent to %s target(s)", len(sent))
            return {"status": "sent", "sent": len(sent), "results": sent}
        if sent:
            logger.warning("MAX new order notification partially sent: sent=%s failed=%s", len(sent), len(failed))
            return {"status": "partial", "sent": len(sent), "failed": len(failed), "results": sent, "errors": failed}
        return {"status": "queued", "sent": 0, "failed": len(failed), "errors": failed}

    def get_target(self) -> Optional[Dict[str, str]]:
        if self.target_chat_id:
            return {"chat_id": str(self.target_chat_id)}
        if self.target_user_id:
            return {"user_id": str(self.target_user_id)}
        try:
            with open(self.target_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot read MAX notifier target file %s: %s", self.target_file, exc)
            return None
        if data.get("chat_id"):
            return {"chat_id": str(data["chat_id"])}
        if data.get("user_id"):
            return {"user_id": str(data["user_id"])}
        return None

    def get_targets(self) -> List[Dict[str, str]]:
        targets = []
        primary = self.get_target()
        if primary:
            targets.append(primary)
        for chat_id in self.extra_chat_ids:
            targets.append({"chat_id": str(chat_id)})
        for user_id in self.extra_user_ids:
            targets.append({"user_id": str(user_id)})
        return self._dedupe_targets(targets)

    def save_target(self, *, chat_id: Optional[str], user_id: Optional[str], source_update: Dict[str, Any]) -> Dict[str, str]:
        target: Dict[str, str] = {}
        if chat_id:
            target["chat_id"] = str(chat_id)
        elif user_id:
            target["user_id"] = str(user_id)
        else:
            raise MaxNotificationError("Cannot save empty MAX notification target")
        target.update(
            {
                "saved_at": str(int(time.time() * 1000)),
                "source_update_type": str(source_update.get("update_type") or source_update.get("type") or ""),
            }
        )
        self._ensure_parent_dir(self.target_file)
        with open(self.target_file, "w", encoding="utf-8") as file:
            json.dump(target, file, ensure_ascii=False, indent=2)
        return target

    def enqueue_pending(self, text: str, *, reason: str, target: Optional[Dict[str, str]] = None) -> None:
        payload = {"created_at": int(time.time() * 1000), "reason": reason, "text": text}
        if target:
            payload["target"] = target
        self._ensure_parent_dir(self.pending_file)
        with open(self.pending_file, "a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def flush_pending(self, limit: int = 50) -> Dict[str, int]:
        if not os.path.exists(self.pending_file):
            return {"sent": 0, "remaining": 0}
        with open(self.pending_file, "r", encoding="utf-8") as file:
            rows = [line.strip() for line in file if line.strip()]

        sent = 0
        remaining = []
        for line in rows[:limit]:
            try:
                payload = json.loads(line)
                text = payload.get("text") or ""
                target = payload.get("target")
                if target:
                    self._send_text(text, target)
                    sent += 1
                else:
                    result = self.send_notification(text)
                    if result.get("reason") == "target_missing":
                        remaining.append(line)
                    else:
                        sent += int(result.get("sent") or 0)
            except Exception as exc:
                logger.error("Cannot flush MAX pending notification: %s", exc, exc_info=True)
                remaining.append(line)
        remaining.extend(rows[limit:])

        if remaining:
            with open(self.pending_file, "w", encoding="utf-8") as file:
                file.write("\n".join(remaining) + "\n")
        else:
            try:
                os.remove(self.pending_file)
            except FileNotFoundError:
                pass
        return {"sent": sent, "remaining": len(remaining)}

    def poll_target_forever(self) -> None:
        marker_file = _env("MAX_NOTIFIER_MARKER_FILE", "/var/www/komunal-dom_ru/runtime/max_notifier_marker.txt")
        marker = self._read_text_file(marker_file)
        logger.info("MAX notifier target polling started; marker=%s", marker)
        while True:
            try:
                data = self.get_updates(marker=marker)
                updates = data.get("updates") or []
                for update in updates:
                    target = self.extract_target(update)
                    if not target:
                        continue
                    call_command = self.extract_call_command(update)
                    if call_command:
                        if not self.command_allowed(target):
                            logger.warning("MAX notifier call command ignored from unauthorized target: %s", target)
                            continue
                        self.start_outbound_call_async(call_command["phone"], target)
                        logger.info("MAX notifier outbound call command accepted: phone=%s target=%s", call_command["phone"], target)
                        continue
                    if not self.bind_allowed(update):
                        logger.info("MAX notifier bind update ignored: bind code mismatch")
                        continue
                    saved = self.save_target(
                        chat_id=target.get("chat_id"),
                        user_id=target.get("user_id"),
                        source_update=update,
                    )
                    self._send_text("Канал уведомлений подключен. Новые заявки будут приходить сюда.", saved)
                    flushed = self.flush_pending()
                    logger.info("MAX notifier target saved: %s; flushed=%s", saved, flushed)
                marker = data.get("marker") or marker
                if marker:
                    self._write_text_file(marker_file, str(marker))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.error("MAX notifier target polling failed: %s", exc, exc_info=True)
                time.sleep(5)

    def extract_target(self, update: Dict[str, Any]) -> Optional[Dict[str, str]]:
        if not isinstance(update, dict):
            return None
        update_type = str(update.get("update_type") or update.get("type") or "")
        if update_type not in {"message_created", "bot_started"}:
            return None
        message = update.get("message") or {}
        sender = message.get("sender") or update.get("user") or {}
        recipient = message.get("recipient") or {}
        chat_id = self._first_value(
            update.get("chat_id"),
            update.get("chatId"),
            recipient.get("chat_id"),
            recipient.get("chatId"),
            message.get("chat_id"),
        )
        user_id = self._first_value(
            sender.get("user_id"),
            sender.get("id"),
            update.get("user_id"),
            update.get("userId"),
        )
        if chat_id:
            return {"chat_id": str(chat_id), "user_id": str(user_id) if user_id else ""}
        if user_id:
            return {"user_id": str(user_id)}
        return None

    def bind_allowed(self, update: Dict[str, Any]) -> bool:
        bind_code = _env("MAX_NOTIFIER_BIND_CODE")
        if not bind_code:
            return True
        message = update.get("message") or {}
        body = message.get("body") or update.get("body") or {}
        text = str(body.get("text") or message.get("text") or update.get("text") or "")
        return bind_code in text

    def extract_call_command(self, update: Dict[str, Any]) -> Optional[Dict[str, str]]:
        text = self.extract_text(update)
        match = re.match(r"^\s*--\s*вызов\s+(.+?)\s*$", text, flags=re.IGNORECASE)
        if not match:
            return None
        phone = self.normalize_phone(match.group(1))
        if not phone:
            return {"phone": "", "error": "invalid_phone"}
        return {"phone": phone}

    def extract_text(self, update: Dict[str, Any]) -> str:
        message = update.get("message") or {}
        body = message.get("body") or update.get("body") or {}
        return str(body.get("text") or message.get("text") or update.get("text") or "")

    def normalize_phone(self, raw_phone: str) -> Optional[str]:
        value = str(raw_phone or "").strip()
        match = re.search(r"\+?\d[\d\s().-]{5,}\d", value)
        if not match:
            return None
        phone = re.sub(r"[\s().-]+", "", match.group(0))
        if phone.startswith("+"):
            digits = phone[1:]
        else:
            digits = phone
        if not digits.isdigit() or not 10 <= len(digits) <= 15:
            return None
        return f"+{digits}" if phone.startswith("+") else digits

    def command_allowed(self, source_target: Dict[str, str]) -> bool:
        allowed_targets = self.get_targets()
        if not allowed_targets:
            return False
        source_keys = {
            key
            for key in (
                f"chat:{source_target.get('chat_id')}" if source_target.get("chat_id") else None,
                f"user:{source_target.get('user_id')}" if source_target.get("user_id") else None,
            )
            if key
        }
        allowed_keys = {self._target_key(target) for target in allowed_targets}
        return bool(source_keys.intersection(key for key in allowed_keys if key))

    def start_outbound_call_async(self, phone: str, reply_target: Dict[str, str]) -> None:
        if not phone:
            self._send_text("Вызов не выполнен - не удалось выделить номер телефона.", reply_target)
            return
        worker = threading.Thread(
            target=self._outbound_call_worker,
            args=(phone, dict(reply_target)),
            daemon=True,
            name=f"max-notifier-call-{phone[-4:]}",
        )
        worker.start()

    def _outbound_call_worker(self, phone: str, reply_target: Dict[str, str]) -> None:
        try:
            result = self.call_asterisk(phone)
            status_text = str(result.get("status") or result.get("result") or "ответ получен").strip()
            response_phone = str(result.get("phone") or phone)
            text = f"Вызов на номер {response_phone} - {status_text}"
        except Exception as exc:
            logger.error("Asterisk outbound call failed: %s", exc, exc_info=True)
            text = f"Вызов на номер {phone} - ошибка: {exc}"
        try:
            self._send_text(text, reply_target)
        except Exception as exc:
            logger.error("Cannot send MAX outbound call result: %s", exc, exc_info=True)

    def call_asterisk(self, phone: str) -> Dict[str, Any]:
        token = self.get_asterisk_call_token()
        if not token:
            raise MaxNotificationError("не настроен контрольный токен Asterisk")
        payload = {
            "token": token,
            "phone": phone,
        }
        timeout = self._asterisk_call_timeout()
        request = urllib.request.Request(
            self.asterisk_call_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise MaxNotificationError(f"Asterisk HTTP {exc.code}: {raw_error[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise MaxNotificationError(f"Asterisk request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise MaxNotificationError("Asterisk returned invalid JSON") from exc
        return data if isinstance(data, dict) else {"status": str(data)}

    def get_asterisk_call_token(self) -> Optional[str]:
        if self.asterisk_call_token:
            return self.asterisk_call_token
        try:
            from django.conf import settings

            tokens = getattr(settings, "EXTERNAL_API_TOKENS", {}) or {}
            token = self._find_asterisk_token(tokens)
            if token:
                return token
        except Exception:
            pass
        try:
            from message_handler.views import API_TOKENS

            token = self._find_asterisk_token(API_TOKENS)
            if token:
                return token
        except Exception:
            pass
        return None

    def _find_asterisk_token(self, tokens: Dict[str, Any]) -> Optional[str]:
        if not isinstance(tokens, dict):
            return None
        for token, system_name in tokens.items():
            if str(system_name) == "asterisk_integration":
                return str(token)
        for token in tokens:
            return str(token)
        return None

    def _asterisk_call_timeout(self) -> int:
        raw_timeout = _env("ASTERISK_OUTBOUND_CALL_TIMEOUT", str(DEFAULT_ASTERISK_CALL_TIMEOUT))
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            return DEFAULT_ASTERISK_CALL_TIMEOUT
        return max(5, min(timeout, 60))

    def get_me(self) -> Dict[str, Any]:
        return self._api_request("GET", "/me")

    def get_chats(self) -> Dict[str, Any]:
        return self._api_request("GET", "/chats")

    def get_updates(self, *, marker: Optional[str] = None, limit: int = 50, timeout: int = 30) -> Dict[str, Any]:
        params = {"limit": str(limit), "timeout": str(timeout), "types": "message_created,bot_started"}
        if marker:
            params["marker"] = str(marker)
        return self._api_request("GET", "/updates", params=params, timeout=timeout + 10)

    def _send_text(self, text: str, target: Dict[str, str]) -> Dict[str, Any]:
        if not text:
            return {"status": "ignored", "reason": "empty_text"}
        params = {}
        if target.get("chat_id"):
            params["chat_id"] = str(target["chat_id"])
        elif target.get("user_id"):
            params["user_id"] = str(target["user_id"])
        else:
            raise MaxNotificationError("MAX notification target is missing")
        return self._api_request("POST", "/messages", params=params, body={"text": text, "notify": True})

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        if not self.token:
            raise MaxNotificationError("MAX_NOTIFIER_BOT_TOKEN is not configured")
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Authorization": self.token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.api_base_url}{path}{query}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {"success": True}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise MaxNotificationError(f"MAX API HTTP {exc.code}: {raw_error[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise MaxNotificationError(f"MAX API request failed: {exc}") from exc

    def _ensure_parent_dir(self, path: str) -> None:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _read_text_file(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as file:
                value = file.read().strip()
                return value or None
        except FileNotFoundError:
            return None

    def _write_text_file(self, path: str, value: str) -> None:
        self._ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as file:
            file.write(value)

    def _split_ids(self, value: Optional[str]) -> List[str]:
        if not value:
            return []
        return [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]

    def _dedupe_targets(self, targets: List[Dict[str, str]]) -> List[Dict[str, str]]:
        result = []
        seen = set()
        for target in targets:
            key = self._target_key(target)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(target)
        return result

    def _target_key(self, target: Dict[str, str]) -> Optional[str]:
        if target.get("chat_id"):
            return f"chat:{target['chat_id']}"
        if target.get("user_id"):
            return f"user:{target['user_id']}"
        return None

    def _first_value(self, *values: Any) -> Optional[Any]:
        for value in values:
            if value is not None and value != "":
                return value
        return None


def notify_new_work_order_by_id(work_order_id: int) -> Dict[str, Any]:
    return MaxNotificationService().notify_new_work_order_by_id(work_order_id)


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "komunal_dom.settings")
    import django

    django.setup()


def main() -> None:
    parser = argparse.ArgumentParser(description="MAX new work order notifier")
    parser.add_argument("--me", action="store_true")
    parser.add_argument("--chats", action="store_true")
    parser.add_argument("--poll-target", action="store_true")
    parser.add_argument("--flush-pending", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    setup_django()
    service = MaxNotificationService()
    if args.me:
        print(json.dumps(service.get_me(), ensure_ascii=False, indent=2))
    elif args.chats:
        print(json.dumps(service.get_chats(), ensure_ascii=False, indent=2))
    elif args.flush_pending:
        print(json.dumps(service.flush_pending(), ensure_ascii=False, indent=2))
    elif args.poll_target:
        service.poll_target_forever()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
