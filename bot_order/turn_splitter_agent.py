import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from .llm_client import LiteLLMClient


class TurnSplitterAgent:
    """Splits a resident turn into address, problem and contact parts."""

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm

    async def analyze(
        self,
        *,
        text: str,
        state: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        result = await self.llm.function_call(
            system_prompt=self._function_system_prompt(),
            user_prompt=self._build_function_user_prompt(text=text, state=state),
            function_name="emit_turn_parts",
            function_description="Разложить текущую реплику жильца на адрес, проблему и контакт.",
            parameters=self._function_schema(),
            session_id=session_id,
            message_id=message_log_id,
            caller_service="TurnSplitterAgent.analyze",
            prompt_slug="turn-splitter-lite",
            max_tokens=320,
            temperature=0.0,
        )
        return self._normalize_result(text, result, state)

    def _normalize_result(self, text: str, result: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        address = result.get("address") if isinstance(result.get("address"), dict) else {}
        problem = result.get("problem") if isinstance(result.get("problem"), dict) else {}
        contact = result.get("contact") if isinstance(result.get("contact"), dict) else {}
        flags = result.get("flags") if isinstance(result.get("flags"), dict) else {}

        address_text = self._clean(address.get("text")) or self._clean(result.get("address_text"))
        problem_text = self._clean(problem.get("text")) or self._clean(result.get("problem_text"))
        contact_text = self._clean(contact.get("text")) or self._clean(result.get("contact_text"))

        address_text = self._grounded_or_empty(text, address_text)
        problem_text = self._grounded_or_empty(text, problem_text)
        contact_text = self._grounded_or_empty(text, contact_text)

        address_change_attempt = self._bool(flags.get("address_change_attempt"), result.get("address_change_attempt"))
        separate_order_possible = self._bool(flags.get("separate_order_possible"), result.get("separate_order_possible"))
        has_address = (self._bool(address.get("present"), result.get("has_address")) or self._payload_has_value(address)) and bool(address_text)
        has_problem = (self._bool(problem.get("present"), result.get("has_problem")) or bool(problem_text)) and bool(problem_text)
        has_contact = (self._bool(contact.get("present"), result.get("has_contact")) or self._payload_has_value(contact)) and bool(contact_text)
        if self._should_drop_address_noise(
            state=state or {},
            has_address=has_address,
            has_problem=has_problem,
            address=address,
            address_change_attempt=address_change_attempt,
        ):
            has_address = False
            address_text = ""
            address = {}
        primary_intent = self._primary_intent(has_address=has_address, has_problem=has_problem, has_contact=has_contact)
        return {
            "primary_intent": primary_intent,
            "has_address": has_address,
            "has_problem": has_problem,
            "has_contact": has_contact,
            "address_text": address_text,
            "problem_text": problem_text,
            "contact_text": contact_text,
            "address": self._normalize_address_payload(address, address_text, has_address, text),
            "problem": {"present": has_problem, "text": problem_text},
            "contact": self._normalize_contact_payload(contact, contact_text, has_contact),
            "answers_current_question": self._bool(result.get("answers_current_question")),
            "address_change_attempt": address_change_attempt,
            "separate_order_possible": separate_order_possible,
            "reason": result.get("reason") or "",
            "raw": result.get("_raw_response"),
            "source_text": text or "",
        }

    def _should_drop_address_noise(
        self,
        *,
        state: Dict[str, Any],
        has_address: bool,
        has_problem: bool,
        address: Dict[str, Any],
        address_change_attempt: bool,
    ) -> bool:
        if not has_address or not has_problem or address_change_attempt:
            return False
        known_address = state.get("address_input") or {}
        address_is_ready = bool(known_address.get("city") and known_address.get("street") and known_address.get("house"))
        if not address_is_ready:
            return False
        return not bool(self._clean(address.get("flat")))

    def _clean(self, value: Any) -> str:
        if value in (None, False):
            return ""
        return str(value).strip()

    def _bool(self, *values: Any) -> bool:
        for value in values:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"true", "1", "yes", "да"}:
                    return True
                if normalized in {"false", "0", "no", "нет", ""}:
                    return False
            if value is not None:
                return bool(value)
        return False

    def _primary_intent(self, *, has_address: bool, has_problem: bool, has_contact: bool) -> str:
        if has_address and not has_problem and not has_contact:
            return "address_update"
        if has_problem and not has_address and not has_contact:
            return "problem_detail"
        if has_contact and not has_address and not has_problem:
            return "contact_update"
        if has_address or has_problem or has_contact:
            return "mixed"
        return "unknown"

    def _payload_has_value(self, payload: Dict[str, Any]) -> bool:
        return any(self._clean(value) for key, value in payload.items() if key != "present")

    def _normalize_address_payload(self, address: Dict[str, Any], address_text: str, has_address: bool, source_text: str = "") -> Dict[str, Any]:
        if not has_address:
            return {"present": False, "text": "", "city": None, "street": None, "house": None, "flat": None}
        city = self._clean(address.get("city"))
        street = self._clean(address.get("street"))
        house = self._clean(address.get("house"))
        flat = self._clean(address.get("flat"))
        city = city if self._looks_grounded(source_text, city) else ""
        street = street if self._looks_grounded(source_text, street) else ""
        house = house if self._looks_grounded(source_text, house) else ""
        flat = flat if self._looks_grounded(source_text, flat) and self._has_flat_marker(source_text) else ""
        return {
            "present": has_address,
            "text": address_text,
            "city": city or None,
            "street": street or None,
            "house": house or None,
            "flat": flat or None,
        }

    def _normalize_contact_payload(self, contact: Dict[str, Any], contact_text: str, has_contact: bool) -> Dict[str, Any]:
        if not has_contact:
            return {"present": False, "text": "", "name": None, "phone": None, "method": None}
        return {
            "present": has_contact,
            "text": contact_text,
            "name": self._clean(contact.get("name")) or None,
            "phone": self._clean(contact.get("phone")) or None,
            "method": self._clean(contact.get("method")) or None,
        }

    def _has_flat_marker(self, text: str) -> bool:
        return bool(re.search(r"\b(?:кв\.?|квартир\w*|пом\.?|помещени\w*)\b", text or "", flags=re.IGNORECASE))

    def _grounded_or_empty(self, source_text: str, value: str) -> str:
        if not value:
            return ""
        if self._looks_grounded(source_text, value):
            return value
        return ""

    def _looks_grounded(self, source_text: str, value: str) -> bool:
        source = self._normalize_for_overlap(source_text)
        candidate = self._normalize_for_overlap(value)
        if not source or not candidate:
            return False
        if candidate in source:
            return True
        source_tokens = source.split()
        candidate_tokens = candidate.split()
        if not source_tokens or not candidate_tokens:
            return False
        matched = 0
        for candidate_token in candidate_tokens:
            if any(self._tokens_match(candidate_token, source_token) for source_token in source_tokens):
                matched += 1
        return matched > 0 and matched / max(len(candidate_tokens), 1) >= 0.45

    def _tokens_match(self, left: str, right: str) -> bool:
        if left == right:
            return True
        if len(left) < 3 or len(right) < 3:
            return False
        return SequenceMatcher(None, left, right).ratio() >= 0.72

    def _normalize_for_overlap(self, value: str) -> str:
        normalized = str(value or "").lower().replace("ё", "е")
        normalized = re.sub(r"[^0-9a-zа-я/]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def _default_result(self, text: str) -> Dict[str, Any]:
        return {
            "primary_intent": "unknown",
            "has_address": False,
            "has_problem": False,
            "has_contact": False,
            "address_text": "",
            "problem_text": "",
            "contact_text": "",
            "answers_current_question": False,
            "address_change_attempt": False,
            "separate_order_possible": False,
            "reason": "prompt_missing",
            "raw": None,
            "source_text": text or "",
        }

    def _function_system_prompt(self) -> str:
        return (
            "Ты размечаешь один ответ жильца для заявки ЖКХ. "
            "Выдели только то, что пользователь сказал сейчас: адрес объекта заявки, описание проблемы, контакт. "
            "Контекст нужен только для понимания ответа; не копируй из вопроса или известных фактов адрес, имя, телефон или проблему. "
            "Значения бери только из ответа жильца либо из очевидного исправления его синтаксической/STT-ошибки. "
            "По умолчанию ответ связан с вопросом бота, но в нем могут быть дополнительные сведения. "
            "Адрес — только город, улица, дом, корпус, строение, квартира/помещение объекта заявки. "
            "Проблема — любая авария, поломка, отсутствие услуги, повреждение, дерево/мусор/вода/свет/газ/лифт, место проявления и последствия. "
            "Если в реплике есть описание проблемы, обязательно заполни problem.text и problem.present=true, даже если бот спрашивал адрес или контакт. "
            "Не превращай слова из описания происшествия в улицу или дом. "
            "Номер подъезда, подвала, двора, входа, лестницы — локализация проблемы, а не номер дома. "
            "Если в address есть text/city/street/house/flat, address.present должен быть true даже при неполном адресе. "
            "Если в problem есть text, problem.present должен быть true. Если в contact есть text/name/phone/method, contact.present должен быть true. "
            "Заполни аргументы функции emit_turn_parts; отсутствующие строки оставляй пустыми."
        )

    def _build_function_user_prompt(self, *, text: str, state: Dict[str, Any]) -> str:
        address = state.get("address_input") or {}
        contact = state.get("contact") or {}
        problem = state.get("problem") or {}
        dialog_context = state.get("dialog_context") or {}
        known_facts = {
            "address": {
                "has_city": bool(address.get("city")),
                "has_street": bool(address.get("street")),
                "has_house": bool(address.get("house")),
                "has_flat": bool(address.get("flat")),
            },
            "problem": {"present": bool(problem.get("txtPrb"))},
            "contact": {
                "has_name": bool(contact.get("name") or contact.get("candidate_name")),
                "has_phone": bool(contact.get("phone") or contact.get("source_phone") or contact.get("candidate_phone")),
            },
        }
        return (
            f"Вопрос бота: {dialog_context.get('last_bot_question') or ''}\n"
            f"Известные факты: {json.dumps(known_facts, ensure_ascii=False, separators=(',', ':'))}\n"
            f"Ответ жильца: {text or ''}"
        )

    def _function_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answers_current_question": {
                    "type": "boolean",
                    "description": "Ответ связан с последним вопросом бота.",
                },
                "address": {
                    "type": "object",
                    "description": "Адресная часть, сказанная в текущей реплике.",
                    "properties": {
                        "present": {"type": "boolean"},
                        "text": {"type": "string", "description": "Адресный фрагмент из реплики или пустая строка."},
                        "city": {"type": "string", "description": "Населенный пункт или пустая строка."},
                        "street": {"type": "string", "description": "Улица без служебного слова или пустая строка."},
                        "house": {"type": "string", "description": "Номер дома или пустая строка."},
                        "flat": {"type": "string", "description": "Квартира/помещение или пустая строка."},
                    },
                    "required": ["present", "text", "city", "street", "house", "flat"],
                },
                "problem": {
                    "type": "object",
                    "description": "Описание проблемы из текущей реплики.",
                    "properties": {
                        "present": {"type": "boolean"},
                        "text": {"type": "string", "description": "Фрагмент проблемы или пустая строка."},
                    },
                    "required": ["present", "text"],
                },
                "contact": {
                    "type": "object",
                    "description": "Контактная информация из текущей реплики.",
                    "properties": {
                        "present": {"type": "boolean"},
                        "text": {"type": "string", "description": "Контактный фрагмент или пустая строка."},
                        "name": {"type": "string", "description": "Имя контакта или пустая строка."},
                        "phone": {"type": "string", "description": "Телефон или пустая строка."},
                        "method": {"type": "string", "description": "Способ связи или пустая строка."},
                    },
                    "required": ["present", "text", "name", "phone", "method"],
                },
                "flags": {
                    "type": "object",
                    "properties": {
                        "address_change_attempt": {"type": "boolean"},
                        "separate_order_possible": {"type": "boolean"},
                    },
                    "required": ["address_change_attempt", "separate_order_possible"],
                },
                "reason": {"type": "string", "description": "Краткое объяснение разметки."},
            },
            "required": ["answers_current_question", "address", "problem", "contact", "flags", "reason"],
        }

    async def _build_prompt(self, *, text: str, state: Dict[str, Any]) -> str:
        template = await self._load_prompt_template("turn-splitter-lite")
        if not template:
            template = self._fallback_template()
        address = state.get("address_input") or {}
        contact = state.get("contact") or {}
        problem = state.get("problem") or {}
        dialog_context = state.get("dialog_context") or {}
        known_facts = {
            "address": {
                "has_city": bool(address.get("city")),
                "has_street": bool(address.get("street")),
                "has_house": bool(address.get("house")),
                "has_flat": bool(address.get("flat")),
            },
            "problem": {"present": bool(problem.get("txtPrb"))},
            "contact": {
                "has_name": bool(contact.get("name") or contact.get("candidate_name")),
                "has_phone": bool(contact.get("phone") or contact.get("source_phone") or contact.get("candidate_phone")),
            },
        }
        known_facts_json = json.dumps(known_facts, ensure_ascii=False, separators=(",", ":"))
        return (
            template
            .replace("{last_bot_question}", str(dialog_context.get("last_bot_question") or ""))
            .replace("{known_facts}", known_facts_json)
            .replace("{stage}", "")
            .replace("{last_bot_action}", "")
            .replace("{known_address}", "")
            .replace("{known_problem}", "")
            .replace("{known_contact_name}", "")
            .replace("{known_contact_phone}", "")
            .replace("{user_message}", text or "")
        )

    def _fallback_template(self) -> str:
        return (
            "Ответь только JSON. Разложи ответ жильца на адрес, проблему и контакт.\n"
            "Вопрос бота: {last_bot_question}\n"
            "Известные факты: {known_facts}\n"
            "Ответ жильца: {user_message}\n"
            "JSON: {\"answers_current_question\":true,\"address\":{\"present\":false,\"text\":\"\",\"city\":null,\"street\":null,\"house\":null,\"flat\":null},"
            "\"problem\":{\"present\":false,\"text\":\"\"},\"contact\":{\"present\":false,\"text\":\"\",\"name\":null,\"phone\":null,\"method\":null},"
            "\"flags\":{\"address_change_attempt\":false,\"separate_order_possible\":false},\"reason\":\"\"}"
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
