import re
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from .llm_client import LiteLLMClient


class ContactAgent:
    """Collects resident contact slots after the serviced address is known."""

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def extract(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        contact = state.setdefault("contact", {})
        if self.is_complete(state):
            return {"has_contact": True, "name": contact.get("name"), "phone": contact.get("phone"), "reason": "already_complete"}

        prompt = await self._build_prompt(state=state, text=text)
        if not prompt:
            return {"has_contact": False, "name": None, "phone": None, "reason": "prompt_missing"}

        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="ContactAgent.slots",
            prompt_slug="contact-slots-lite",
            max_tokens=180,
            temperature=0.0,
        )
        if not self._has_slot_keys(result):
            result = await self.llm.json_call(
                prompt=self._retry_prompt(text=text),
                session_id=session_id,
                message_id=message_log_id,
                caller_service="ContactAgent.slots.retry_json",
                prompt_slug="contact-slots-lite",
                max_tokens=120,
                temperature=0.0,
            )
        name = (result.get("name") or "").strip() or None
        phone = (result.get("phone") or "").strip() or None
        known_phone = contact.get("phone") or contact.get("source_phone") or contact.get("candidate_phone")
        source = (text or "").lower().replace("ё", "е")
        if not phone and known_phone and self._source_references_known_phone(source):
            phone = str(known_phone)
        name, phone = self._drop_ungrounded_slots(
            text=text,
            name=name,
            phone=phone,
            known_phone=known_phone,
        )
        if name:
            contact["name"] = name
        if phone:
            contact["phone"] = phone
        contact.update(
            {
                "status": "complete" if self.is_complete(state) else "incomplete",
                "last_slot_extraction": {
                    "has_contact": bool(name or phone),
                    "name": name,
                    "phone": phone,
                    "reason": result.get("reason") or "",
                    "raw": result.get("_raw_response"),
                },
            }
        )
        return contact["last_slot_extraction"]

    def _has_slot_keys(self, result: Dict[str, Any]) -> bool:
        return any(key in result for key in ("has_contact", "name", "phone"))

    def _retry_prompt(self, *, text: str) -> str:
        return (
            "Верни только один JSON. Первый символ ответа {, последний }. "
            "Не пиши Markdown, комментарии и объяснения.\n"
            "Извлеки из реплики имя и телефон заявителя. Не выдумывай.\n"
            f"Реплика: {text or ''}\n"
            "Схема: {\"has_contact\": true|false, \"name\": string|null, \"phone\": string|null, \"reason\": string}"
        )

    def _drop_ungrounded_slots(
        self,
        *,
        text: str,
        name: Optional[str],
        phone: Optional[str],
        known_phone: Optional[str] = None,
    ):
        source = (text or "").lower().replace("ё", "е")
        if name and name.lower().replace("ё", "е") not in source:
            name = None

        if phone:
            phone_digits = re.sub(r"\D+", "", phone)
            source_digits = re.sub(r"\D+", "", text or "")
            known_digits = re.sub(r"\D+", "", known_phone or "")
            if self._source_references_known_phone(source) and known_digits:
                phone = str(known_phone)
                phone_digits = known_digits
                return name, phone
            local_candidate = self._local_phone_candidate_from_text(text or "", phone_digits)
            if local_candidate:
                phone, phone_digits = local_candidate
            if len(phone_digits) < 5:
                phone = None
            elif len(phone_digits) < 10:
                if phone_digits not in source_digits:
                    phone = None
            elif phone_digits not in source_digits and phone_digits[-10:] not in source_digits:
                phone = None
        return name, phone

    def _source_references_known_phone(self, source: str) -> bool:
        negative_phrases = (
            "не на этот",
            "не этот номер",
            "не по нему",
            "другой номер",
            "другой телефон",
        )
        if any(phrase in source for phrase in negative_phrases):
            return False
        reference_phrases = (
            "этот номер",
            "этот телефон",
            "на этот",
            "на него",
            "по нему",
            "сюда",
            "с которого",
            "с него",
        )
        return any(phrase in source for phrase in reference_phrases)

    def _local_phone_candidate_from_text(self, text: str, phone_digits: str):
        if not phone_digits:
            return None
        for match in re.finditer(r"(?<!\d)(?:\d[\s().-]*){5,9}(?!\d)", text or ""):
            raw = match.group(0).strip()
            digits = re.sub(r"\D+", "", raw)
            if not (5 <= len(digits) < 10):
                continue
            if phone_digits == digits or phone_digits == f"7{digits}":
                return raw, digits
        return None

    def is_complete(self, state: Dict[str, Any]) -> bool:
        contact = state.get("contact") or {}
        return bool((contact.get("name") or "").strip() and (contact.get("phone") or "").strip())

    def missing_fields(self, state: Dict[str, Any]) -> List[str]:
        contact = state.get("contact") or {}
        missing = []
        if not (contact.get("name") or "").strip():
            missing.append("name")
        if not (contact.get("phone") or "").strip():
            missing.append("phone")
        return missing

    def question(self, state: Dict[str, Any]) -> str:
        missing = set(self.missing_fields(state))
        if missing == {"name", "phone"}:
            return "Как к вам обращаться и по какому телефону можно связаться?"
        if "name" in missing:
            return "Как к вам обращаться?"
        if "phone" in missing:
            return "Какой способ связи предпочтителен? Если это MAX или Telegram, напишите номер, к которому привязан аккаунт."
        return ""

    async def _build_prompt(self, *, state: Dict[str, Any], text: str) -> str:
        template = await self._load_prompt_template("contact-slots-lite")
        if not template:
            return ""
        contact = state.get("contact") or {}
        known_phone = contact.get("phone") or contact.get("source_phone") or contact.get("candidate_phone")
        return (
            template
            .replace("{known_name}", str(contact.get("name") or ""))
            .replace("{known_phone}", str(known_phone or ""))
            .replace("{user_message}", text or "")
        )

    async def _load_prompt_template(self, slug: str) -> str:
        def load_sync():
            try:
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT template
                        FROM llm_tester_prompttemplate
                        WHERE slug = %s AND is_active = true
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        [slug],
                    )
                    row = cursor.fetchone()
                return row[0] if row else ""
            except Exception:
                return ""

        return await sync_to_async(load_sync)()
