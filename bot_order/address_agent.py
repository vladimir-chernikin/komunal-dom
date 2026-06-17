import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

from address.models import Building
from address.services import build_full_address, normalize_house_number, normalize_unit_number
from address_extractor_service import AddressExtractor
from work_orders.chat_order.company_resolver import ServiceObjectCompanyResolver

from .fias_logging import fias_log_context
from .llm_client import LiteLLMClient
from .utils import to_float


class AddressAgent:
    ADDRESS_UPDATE_RE = re.compile(
        r"\b(адрес|город|г\.|улица|ул\.|дом|д\.|корпус|корп\.|"
        r"строение|стр\.|литера|лит\.|квартир\w*|кв\.|помещени\w*|пом\.)\b",
        re.IGNORECASE,
    )
    FLAT_ONLY_RE = re.compile(
        r"^\s*(?:кв\.?|квартир\w*|пом\.?|помещени\w*)?\s*\d+[а-яa-z]?\s*$",
        re.IGNORECASE,
    )

    def __init__(self, llm: LiteLLMClient):
        self.llm = llm
        self.extractor = AddressExtractor()
        self.company_resolver = ServiceObjectCompanyResolver()

    async def resolve(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        memory = self._state_address_to_components(state)
        slot_result = await self._extract_address_slots(
            text=text,
            memory=memory,
            state=state,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        components = await sync_to_async(self._components_from_llm_slots)(text, memory, slot_result)
        state.setdefault("address_input", {})["last_slot_extraction"] = slot_result
        validation, fias_log_ids = await sync_to_async(self._validate_sync)(
            components,
            session_id=session_id,
            message_log_id=message_log_id,
        )

        corrected_text = None
        if self._should_try_syntax_correction(validation, components):
            syntax_result = await self._correct_address_syntax(
                text=text,
                components=components,
                validation=validation,
                session_id=session_id,
                message_log_id=message_log_id,
            )
            state.setdefault("address_input", {})["last_syntax_correction"] = syntax_result
            corrected_components = self._components_from_syntax_correction(components, syntax_result)
            if corrected_components and self._syntax_correction_is_safe(
                original=components,
                corrected=corrected_components,
                correction=syntax_result,
            ):
                corrected_validation, corrected_log_ids = await sync_to_async(self._validate_sync)(
                    corrected_components,
                    session_id=session_id,
                    message_log_id=message_log_id,
                )
                syntax_result["validation_status"] = corrected_validation.get("match_status")
                syntax_result["fias_log_ids"] = corrected_log_ids
                if corrected_validation.get("match_status") in {"matched", "not_serviced"}:
                    components = corrected_components
                    validation = corrected_validation
                    fias_log_ids.extend(corrected_log_ids)
                    corrected_text = build_full_address(corrected_components) or corrected_components.get("raw_text")
                    syntax_result["accepted"] = True
                else:
                    syntax_result["accepted"] = False
            elif syntax_result:
                syntax_result["accepted"] = False

        await self._update_state(state, components, validation, fias_log_ids, corrected_text)
        status = validation.get("match_status")
        if status == "matched":
            return {"status": "matched", "message": None, "address_validation": validation, "fias_log_ids": fias_log_ids}
        if status == "not_serviced":
            return {
                "status": "not_serviced",
                "message": "Этот дом найден, но сейчас он не числится в обслуживании вашей УК.",
                "address_validation": validation,
                "fias_log_ids": fias_log_ids,
            }
        return {
            "status": status or "incomplete",
            "message": self._address_question(validation),
            "address_validation": validation,
            "fias_log_ids": fias_log_ids,
        }

    async def update_optional_slots(
        self,
        *,
        state: Dict[str, Any],
        text: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        if not self._looks_like_address_update(state, text):
            return {"status": "skipped", "updated": False, "fias_log_ids": [], "reason": "not_address_update"}

        memory = self._state_address_to_components(state)
        slot_result = await self._extract_address_slots(
            text=text,
            memory=memory,
            state=state,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        state.setdefault("address_input", {})["last_slot_extraction"] = slot_result
        if not slot_result.get("is_address_message"):
            return {"status": "skipped", "updated": False, "fias_log_ids": []}

        components = await sync_to_async(self._components_from_llm_slots)(text, memory, slot_result)
        validation, fias_log_ids = await sync_to_async(self._validate_sync)(
            components,
            session_id=session_id,
            message_log_id=message_log_id,
        )
        apartment_number = components.get("apartment_number")
        previous_apartment = memory.get("apartment_number")
        apartment_added = bool(apartment_number and apartment_number != previous_apartment)
        if (
            apartment_added
            and validation.get("match_status") == "matched"
            and not validation.get("unit_id")
            and (state.get("service_context") or {}).get("service_object_id")
        ):
            state.setdefault("address_input", {}).setdefault("rejected_optional_slots", []).append(
                {
                    "slot": "flat",
                    "value": apartment_number,
                    "reason": "unit_not_found_for_serviced_building",
                }
            )
            return {
                "status": "matched",
                "updated": False,
                "apartment_not_found": True,
                "apartment_number": apartment_number,
                "address_validation": validation,
                "fias_log_ids": fias_log_ids,
            }
        if validation.get("match_status") in {"matched", "not_serviced"}:
            await self._update_state(state, components, validation, fias_log_ids, corrected_text=None)
            return {
                "status": validation.get("match_status"),
                "updated": True,
                "address_validation": validation,
                "fias_log_ids": fias_log_ids,
            }
        return {
            "status": validation.get("match_status") or "incomplete",
            "updated": False,
            "address_validation": validation,
            "fias_log_ids": fias_log_ids,
        }

    def _looks_like_address_update(self, state: Dict[str, Any], text: str) -> bool:
        value = (text or "").strip()
        if not value:
            return False
        if self.ADDRESS_UPDATE_RE.search(value):
            return True

        address = state.get("address_input") or {}
        stage = (state.get("control") or {}).get("stage")
        review_decision = (state.get("review") or {}).get("last_decision") or {}
        review_fields = set(review_decision.get("fields") or [])
        review_expects_address = (
            review_decision.get("action") in {"update_address", "update_multiple"}
            or "address" in review_fields
        )
        if (
            (stage == "pre_registration_review" or review_expects_address)
            and not address.get("flat")
            and self.FLAT_ONLY_RE.match(value)
        ):
            return True
        return False

    async def build_followup_message(
        self,
        *,
        state: Dict[str, Any],
        address_result: Dict[str, Any],
        user_message: str,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Optional[str]:
        prompt = await self._build_followup_prompt(
            state=state,
            address_result=address_result,
            user_message=user_message,
        )
        if not prompt:
            return None
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="AddressAgent.followup",
            prompt_slug="address-followup-lite",
            max_tokens=180,
            temperature=0.2,
        )
        message = (result.get("message") or result.get("_raw_response") or "").strip().strip("`")
        return self._polish_followup_message(
            message=message,
            state=state,
            address_result=address_result,
        )

    def _components_from_llm_slots(
        self,
        text: str,
        memory: Dict[str, Any],
        slot_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        components = {
            "region": memory.get("region"),
            "city": memory.get("city"),
            "street": memory.get("street"),
            "house_number": memory.get("house_number"),
            "apartment_number": memory.get("apartment_number"),
            "raw_text": text,
            "_current_message_has_address": False,
        }
        if not slot_result.get("is_address_message"):
            return components

        for target, source in {
            "city": "city",
            "street": "street",
            "house_number": "house_number",
            "apartment_number": "apartment_number",
        }.items():
            value = slot_result.get(source)
            if value not in (None, ""):
                components[target] = value
        if components.get("house_number"):
            components["house_number"] = normalize_house_number(
                self._normalize_spoken_number_slot(components.get("house_number"))
            )
        if components.get("apartment_number"):
            components["apartment_number"] = normalize_unit_number(
                self._normalize_spoken_number_slot(components.get("apartment_number"))
            )
        components["_current_message_has_address"] = True
        return components

    def _validate_sync(self, components: Dict[str, Any], *, session_id: str, message_log_id: Optional[int]):
        log_ids = []
        with fias_log_context(
            session_id=session_id,
            message_log_id=message_log_id,
            state_stage="address_validate_fias",
            log_ids=log_ids,
        ):
            validation = self.extractor.validate_and_match_to_db(components)
        return validation, log_ids

    async def _extract_address_slots(
        self,
        *,
        text: str,
        memory: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        system_prompt = self._slot_function_system_prompt()
        user_prompt = self._build_slot_function_user_prompt(text=text, memory=memory, state=state)
        result = await self.llm.function_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            function_name="emit_address_slots",
            function_description="Вернуть новые или исправленные адресные слоты из текущей реплики жильца.",
            parameters=self._slot_function_schema(),
            session_id=session_id,
            message_id=message_log_id,
            caller_service="AddressAgent.slots",
            prompt_slug="address-slots-lite",
            max_tokens=260,
            temperature=0.0,
        )
        city, city_evidence = self._slot_value_from_result(result.get("city"))
        street, street_evidence = self._slot_value_from_result(result.get("street"))
        house_number, house_evidence = self._slot_value_from_result(result.get("house_number"))
        apartment_number, apartment_evidence = self._slot_value_from_result(result.get("apartment_number"))
        if house_number:
            house_number = self._normalize_spoken_number_slot(house_number)
            house_evidence = self._normalize_house_evidence_from_function_call(
                value=house_number,
                evidence=house_evidence,
            )
        if apartment_number:
            apartment_number = self._normalize_spoken_number_slot(apartment_number)
            if not self._has_apartment_marker(text):
                apartment_number = None
                apartment_evidence = None
        rejected_slots = []
        slot_values = {
            "city": [city, city_evidence],
            "street": [street, street_evidence],
            "house_number": [house_number, house_evidence],
            "apartment_number": [apartment_number, apartment_evidence],
        }
        if city and street and self._normalized_for_evidence(city) == self._normalized_for_evidence(street):
            rejected_slots.append({"slot": "city", "value": city, "evidence": city_evidence, "reason": "duplicates_street"})
            slot_values["city"][0] = None
        for key, item in slot_values.items():
            value, evidence = item
            if not value:
                continue
            if not self._slot_is_grounded_in_text(text=text, value=value, evidence=evidence):
                rejected_slots.append({"slot": key, "value": value, "evidence": evidence, "reason": "missing_evidence"})
                item[0] = None
        city, street, house_number, apartment_number = [slot_values[key][0] for key in ("city", "street", "house_number", "apartment_number")]
        is_address_message = bool(result.get("is_address_message")) and bool(
            city or street or house_number or apartment_number
        )
        if not is_address_message and any([city, street, house_number, apartment_number]):
            is_address_message = True
        if not is_address_message:
            city = street = house_number = apartment_number = None
        return {
            "is_address_message": is_address_message,
            "city": city,
            "street": street,
            "house_number": house_number,
            "apartment_number": apartment_number,
            "evidence": {
                "city": city_evidence,
                "street": street_evidence,
                "house_number": house_evidence,
                "apartment_number": apartment_evidence,
            },
            "rejected_slots": rejected_slots,
            "reason": result.get("reason") or "",
            "raw": result.get("_raw_response"),
        }

    def _slot_function_system_prompt(self) -> str:
        return (
            "Ты извлекаешь адресные слоты из одной текущей реплики жильца для заявки ЖКХ. "
            "Верни только новые или исправленные части адреса, которые есть в этой реплике. "
            "Известные поля — только контекст наличия данных; не копируй их без evidence из текущей реплики. "
            "В реплике могут быть синтаксические, орфографические и STT-ошибки; исправляй только очевидные. "
            "Населенный пункт может состоять из нескольких слов; не обрезай его до первого слова. "
            "Не угадывай город из названия улицы. Если нет явного маркера города/населенного пункта и бот не спрашивал именно город, city оставь пустым. "
            "Если в реплике есть название рядом с номером дома без маркера города, это обычно street, а не city. "
            "value — значение слота без служебного слова город/г/улица/ул/дом/д. "
            "evidence — точный исходный фрагмент из реплики для этого слота; для номера дома только сам номер дома. "
            "Если slot.value пустой, slot.evidence тоже обязательно пустая строка. "
            "Если найден хотя бы один адресный слот, is_address_message=true. "
            "apartment_number заполняй только если пользователь явно говорит квартиру/кв/помещение. Номер подъезда, входа, подвала или двора не является квартирой. "
            "Заполни аргументы функции emit_address_slots."
        )

    def _build_slot_function_user_prompt(
        self,
        *,
        text: str,
        memory: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
    ) -> str:
        missing_fields = self._slot_missing_fields(memory)
        return (
            f"Последний вопрос бота: {self._expected_address_question(missing_fields)}\n"
            f"Недостающие поля адреса: {', '.join(missing_fields) or 'нет'}\n"
            "Известные поля адреса: "
            f"city={self._known_slot_marker(memory.get('city'))}; "
            f"street={self._known_slot_marker(memory.get('street'))}; "
            f"house={self._known_slot_marker(memory.get('house_number'))}; "
            f"flat={self._known_slot_marker(memory.get('apartment_number'))}\n"
            f"Реплика жильца: {text or ''}"
        )

    def _slot_function_schema(self) -> Dict[str, Any]:
        slot_schema = {
            "type": "object",
            "properties": {
                "value": {"type": "string", "description": "Значение слота или пустая строка."},
                "evidence": {"type": "string", "description": "Точный фрагмент реплики для слота или пустая строка."},
            },
            "required": ["value", "evidence"],
        }
        return {
            "type": "object",
            "properties": {
                "is_address_message": {
                    "type": "boolean",
                    "description": "В реплике есть новая или исправленная часть адреса.",
                },
                "city": slot_schema,
                "street": slot_schema,
                "house_number": slot_schema,
                "apartment_number": slot_schema,
                "reason": {"type": "string", "description": "Краткое пояснение разбора."},
            },
            "required": ["is_address_message", "city", "street", "house_number", "apartment_number", "reason"],
        }

    def _address_slot_contract_issue(self, *, text: str, result: Dict[str, Any]) -> str:
        if not result:
            return ""
        street, street_evidence = self._slot_value_from_result(result.get("street"))
        city, _city_evidence = self._slot_value_from_result(result.get("city"))
        house_number, house_evidence = self._slot_value_from_result(result.get("house_number"))
        issues = []
        if street and re.search(r"\b(?:город|горд|г|улица|ул)\b\.?", street, flags=re.IGNORECASE):
            issues.append("street.value содержит служебное слово или часть другого слота")
        evidence_text = " ".join(part for part in [street_evidence, house_evidence] if part)
        source_text = text or ""
        if not city and re.search(r"\b(?:город|горд|г)\b\.?\s+[a-zа-яё-]+", source_text, flags=re.IGNORECASE):
            issues.append("в реплике есть маркер города, city должен быть словом после этого маркера")
        if street_evidence and re.search(r"\b(?:улица|ул)\b\.?", street_evidence, flags=re.IGNORECASE):
            if not re.match(r"^\s*(?:улица|ул)\b\.?\s+[a-zа-яё-]+", street_evidence, flags=re.IGNORECASE):
                issues.append("street.evidence захватывает слова до маркера улицы")
        if not city and re.search(r"\b(?:город|горд|г)\b\.?", evidence_text, flags=re.IGNORECASE):
            issues.append("в evidence есть маркер города, но city не заполнен")
        if house_number and house_evidence:
            evidence_norm = self._normalized_for_evidence(house_evidence)
            house_norm = self._normalized_for_evidence(str(house_number))
            if house_norm and evidence_norm and house_norm != evidence_norm:
                issues.append("house_number.evidence должен быть только номером дома")
        return "; ".join(issues)

    def _slot_value_from_result(self, slot: Any):
        if isinstance(slot, dict):
            value = slot.get("value")
            evidence = slot.get("evidence")
        else:
            value = slot
            evidence = None
        value = str(value).strip() if value not in (None, "") else None
        evidence = str(evidence).strip() if evidence not in (None, "") else None
        if self._is_empty_function_slot(value):
            value = None
        if self._is_empty_function_slot(evidence):
            evidence = None
        return value, evidence

    def _is_empty_function_slot(self, value: Optional[str]) -> bool:
        normalized = str(value or "").strip().lower().replace("ё", "е").strip(" .,:;!?")
        return (
            normalized in {
                "",
                "null",
                "none",
                "нет",
                "нет значения",
                "нет evidence",
                "отсутствует",
                "не указано",
                "уже известно",
            }
            or normalized.startswith("точный фрагмент")
            or normalized.startswith("точная реплика")
            or normalized.endswith("пустая строка")
        )

    def _normalize_house_evidence_from_function_call(self, *, value: Optional[str], evidence: Optional[str]) -> Optional[str]:
        if not value or not evidence:
            return evidence
        house_norm = self._normalized_for_evidence(str(value))
        evidence_norm = self._normalized_for_evidence(str(evidence))
        if house_norm and evidence_norm and house_norm in evidence_norm.split():
            return str(value)
        return evidence

    def _has_apartment_marker(self, text: str) -> bool:
        return bool(re.search(r"\b(?:кв\.?|квартир\w*|пом\.?|помещени\w*)\b", text or "", flags=re.IGNORECASE))

    def _slot_is_grounded_in_text(self, *, text: str, value: str, evidence: Optional[str]) -> bool:
        source = self._normalized_for_evidence(text)
        if not source:
            return False
        if evidence:
            evidence_norm = self._normalized_for_evidence(evidence)
            if evidence_norm and evidence_norm in source:
                return True
            return self._evidence_token_overlap(evidence_norm, source)
        value_norm = self._normalized_for_evidence(value)
        return bool(value_norm and value_norm in source)

    def _normalized_for_evidence(self, value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zа-яё/]+", " ", str(value or "").lower().replace("ё", "е"))).strip()

    def _evidence_token_overlap(self, evidence_norm: str, source_norm: str) -> bool:
        evidence_tokens = [token for token in evidence_norm.split() if len(token) >= 2]
        if not evidence_tokens:
            return False
        return any(token in source_norm.split() for token in evidence_tokens)

    async def _build_slot_prompt(
        self,
        *,
        text: str,
        memory: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
    ) -> str:
        template = await self._load_prompt_template("address-slots-lite")
        if not template:
            return ""
        missing_fields = self._slot_missing_fields(memory)
        last_bot_question = self._expected_address_question(missing_fields)
        return (
            template
            .replace("{known_city}", self._known_slot_marker(memory.get("city")))
            .replace("{known_street}", self._known_slot_marker(memory.get("street")))
            .replace("{known_house}", self._known_slot_marker(memory.get("house_number")))
            .replace("{known_flat}", self._known_slot_marker(memory.get("apartment_number")))
            .replace("{missing_fields}", ", ".join(missing_fields) or "нет")
            .replace("{last_bot_question}", last_bot_question)
            .replace("{user_message}", text or "")
        )

    def _known_slot_marker(self, value: Any) -> str:
        return "уже известно" if value not in (None, "") else ""

    def _slot_missing_fields(self, memory: Dict[str, Any]) -> list:
        missing = []
        if not memory.get("city"):
            missing.append("city/населенный пункт")
        if not memory.get("street"):
            missing.append("street/улица")
        if not memory.get("house_number"):
            missing.append("house_number/номер дома")
        return missing

    def _expected_address_question(self, missing_fields: list) -> str:
        if not missing_fields:
            return ""
        if missing_fields == ["city/населенный пункт"]:
            return "Уточните населенный пункт."
        if missing_fields == ["street/улица"]:
            return "Уточните улицу."
        if missing_fields == ["house_number/номер дома"]:
            return "Уточните номер дома."
        if len(missing_fields) == 3:
            return "По какому адресу хотите оставить обращение?"
        return "Уточните недостающие части адреса."

    async def _build_followup_prompt(self, *, state: Dict[str, Any], address_result: Dict[str, Any], user_message: str) -> str:
        template = await self._load_prompt_template("address-followup-lite")
        if not template:
            return ""
        address = state.get("address_input") or {}
        validation = address_result.get("address_validation") or {}
        missing = self._missing_address_parts(address)
        return (
            template
            .replace("{user_message}", user_message or "")
            .replace("{txtPrb}", ((state.get("problem") or {}).get("txtPrb") or ""))
            .replace("{known_city}", str(address.get("city") or ""))
            .replace("{known_street}", str(address.get("street") or ""))
            .replace("{known_house}", str(address.get("house") or ""))
            .replace("{known_flat}", str(address.get("flat") or ""))
            .replace("{missing_parts}", ", ".join(missing) or "адрес")
            .replace("{status}", str(address_result.get("status") or ""))
            .replace("{reason}", str(validation.get("reason") or ""))
        )

    async def _correct_address_text(
        self,
        *,
        text: str,
        candidate_hints,
        session_id: str,
        message_log_id: Optional[int],
    ) -> Optional[str]:
        prompt = await self._build_correction_prompt(text=text, candidate_hints=candidate_hints)
        if not prompt:
            return None
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="AddressAgent.correction",
            prompt_slug="address-correction-lite",
            max_tokens=350,
            temperature=0.1,
        )
        corrected_text = (result.get("corrected_text") or "").strip()
        if (
            result.get("changed")
            and to_float(result.get("confidence")) >= 0.65
            and corrected_text
            and self._address_correction_is_safe(text, corrected_text)
        ):
            return corrected_text
        return None

    async def _build_correction_prompt(self, *, text: str, candidate_hints) -> str:
        template = await self._load_prompt_template("address-correction-lite")
        if not template:
            return ""
        hints_text = json.dumps(candidate_hints or [], ensure_ascii=False)
        return template.replace("{text}", text or "").replace("{candidate_hints}", hints_text)

    async def _correct_address_syntax(
        self,
        *,
        text: str,
        components: Dict[str, Any],
        validation: Dict[str, Any],
        session_id: str,
        message_log_id: Optional[int],
    ) -> Dict[str, Any]:
        candidate_hints = await sync_to_async(self._local_candidate_hints)(components, validation)
        prompt = self._build_syntax_correction_prompt(
            text=text,
            components=components,
            validation=validation,
            candidate_hints=candidate_hints,
        )
        result = await self.llm.json_call(
            prompt=prompt,
            session_id=session_id,
            message_id=message_log_id,
            caller_service="AddressAgent.syntax_correction",
            prompt_slug="address-syntax-correction-runtime",
            max_tokens=140,
            temperature=0.0,
        )
        city = (result.get("city") or result.get("город") or "").strip() or None
        street = (result.get("street") or result.get("улица") or "").strip() or None
        house_number = (
            result.get("house_number")
            or result.get("house")
            or result.get("дом")
            or ""
        )
        house_number = str(house_number).strip() or None
        if house_number:
            house_number = self._normalize_spoken_number_slot(house_number)
        correction = {
            "city": city,
            "street": street,
            "house_number": house_number,
            "confidence": to_float(result.get("confidence") or result.get("уверенность")),
            "reasoning": result.get("reasoning") or result.get("reason") or result.get("рассуждение") or "",
            "raw": result.get("_raw_response"),
        }
        return correction

    def _build_syntax_correction_prompt(
        self,
        *,
        text: str,
        components: Dict[str, Any],
        validation: Dict[str, Any],
        candidate_hints,
    ) -> str:
        city = str(components.get("city") or "").strip()
        street = str(components.get("street") or "").strip()
        house = str(components.get("house_number") or "").strip()
        raw_text = str(components.get("raw_text") or text or "").strip()
        reason = validation.get("reason") or "ФИАС не нашел адрес"
        fias_hints = validation.get("fias_candidate_hints") or []
        return (
            "Ты быстрый корректор адреса для УК.\n"
            f"Адрес одной строкой: {raw_text}\n"
            f"Предыдущий разбор: city={city or 'null'}; street={street or 'null'}; house={house or 'null'}\n"
            f"ФИАС: {reason}\n"
            f"ФИАС-подсказки: {json.dumps(fias_hints[:5], ensure_ascii=False)}\n"
            f"Локальные подсказки по уже найденной ФИАС-улице: {json.dumps(candidate_hints or [], ensure_ascii=False)}\n"
            "В адресе может быть ошибка распознавания или написания в городе, улице или доме. "
            "Исправь только очевидную ошибку по смыслу адреса. Не добавляй отсутствующий город, улицу или дом. "
            "Подсказки используй только если все исправленные части похожи на исходную строку. "
            "Не выбирай случайный адрес и не смешивай части разных подсказок. Если уверенности нет, верни исходные поля и confidence < 0.70.\n"
            "Верни только JSON: "
            "{\"city\":string|null,\"street\":string|null,\"house_number\":string|null,"
            "\"confidence\":0.0,\"reasoning\":\"кратко\"}"
        )

    def _local_candidate_hints(self, components: Dict[str, Any], validation: Dict[str, Any], limit: int = 8):
        house_number = normalize_house_number(components.get("house_number"))
        street_guid = validation.get("street_fias_guid")
        if not house_number or not street_guid:
            return []
        if validation.get("match_status") != "not_found":
            return []
        if not components.get("city") or not components.get("street"):
            return []
        try:
            from portal.models import ServiceObject

            buildings = list(
                Building.objects.filter(
                    street_fias_guid=street_guid,
                    house_number=house_number,
                ).order_by("id")[:50]
            )
            active_building_ids = set(
                ServiceObject.objects.filter(
                    is_active=True,
                    building_id__in=[building.id for building in buildings],
                ).values_list("building_id", flat=True)
            )
            candidates = []
            for building in buildings:
                if building.id not in active_building_ids:
                    continue
                candidates.append(building.full_address)
                if len(candidates) >= limit:
                    break
            return candidates
        except Exception:
            return []

    def _single_local_candidate_correction(self, *, raw_text: str, candidate_hints) -> Optional[Dict[str, Any]]:
        if not candidate_hints or len(candidate_hints) != 1:
            return None
        parsed = self._parse_candidate_address(str(candidate_hints[0] or ""))
        if not parsed:
            return None
        if not self._candidate_is_supported_by_raw(raw_text=raw_text, candidate=parsed):
            return None
        return {
            "city": parsed["city"],
            "street": parsed["street"],
            "house_number": parsed["house_number"],
            "confidence": 0.86,
            "reasoning": "single_local_candidate",
            "raw": None,
        }

    def _parse_candidate_address(self, value: str) -> Optional[Dict[str, str]]:
        city_match = re.search(r"\b(?:город|г)\s+([^,]+)", value or "", flags=re.IGNORECASE)
        street_match = re.search(r"\b(?:улица|ул)\.?\s+([^,]+)", value or "", flags=re.IGNORECASE)
        house_match = re.search(r"\b(?:дом|д)\.?\s+([^,]+)", value or "", flags=re.IGNORECASE)
        if not (city_match and street_match and house_match):
            return None
        return {
            "city": city_match.group(1).strip(),
            "street": street_match.group(1).strip(),
            "house_number": normalize_house_number(house_match.group(1).strip()),
        }

    def _candidate_is_supported_by_raw(self, *, raw_text: str, candidate: Dict[str, str]) -> bool:
        tokens = [
            token
            for token in re.findall(r"[a-zа-яё0-9/]+", (raw_text or "").lower().replace("ё", "е"))
            if len(token) >= 3
        ]
        if not tokens:
            return False
        city = self._normalized_for_compare(candidate.get("city"))
        street = self._normalized_for_compare(candidate.get("street"))
        house = self._normalized_for_compare(candidate.get("house_number"))
        raw_norm = self._normalized_for_compare(raw_text)
        if house and house not in raw_norm:
            return False
        city_supported = any(SequenceMatcher(None, city, self._normalized_for_compare(token)).ratio() >= 0.60 for token in tokens)
        street_supported = any(SequenceMatcher(None, street, self._normalized_for_compare(token)).ratio() >= 0.60 for token in tokens)
        return city_supported and street_supported

    def _correction_matches_candidate(self, correction: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        for key in ("city", "street", "house_number"):
            if self._normalized_for_compare(correction.get(key)) != self._normalized_for_compare(candidate.get(key)):
                return False
        return True

    def _components_from_syntax_correction(
        self,
        components: Dict[str, Any],
        correction: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not correction or to_float(correction.get("confidence")) < 0.70:
            return None

        corrected = dict(components)
        changed = False
        for key in ("city", "street", "house_number"):
            value = correction.get(key)
            if value in (None, ""):
                continue
            value = str(value).strip()
            if key == "house_number":
                value = normalize_house_number(self._normalize_spoken_number_slot(value))
            if value and self._normalized_for_compare(value) != self._normalized_for_compare(corrected.get(key)):
                corrected[key] = value
                changed = True

        if not changed:
            return None
        corrected["_current_message_has_address"] = True
        corrected["raw_text"] = build_full_address(corrected) or components.get("raw_text") or ""
        return corrected

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

    def _address_correction_is_safe(self, original: str, corrected: str) -> bool:
        if self._strip_outer_punctuation(original) == self._strip_outer_punctuation(corrected):
            return False

        original_numbers = re.findall(r"\d+", original or "")
        corrected_numbers = re.findall(r"\d+", corrected or "")
        if not original_numbers or not corrected_numbers:
            return True

        def edit_distance_is_small(left: str, right: str) -> bool:
            if abs(len(left) - len(right)) > 1:
                return False
            if left == right:
                return True
            mismatches = 0
            i = j = 0
            while i < len(left) and j < len(right):
                if left[i] == right[j]:
                    i += 1
                    j += 1
                    continue
                mismatches += 1
                if mismatches > 1:
                    return False
                if len(left) > len(right):
                    i += 1
                elif len(right) > len(left):
                    j += 1
                else:
                    i += 1
                    j += 1
            return mismatches + (len(left) - i) + (len(right) - j) <= 1

        for original_number in original_numbers:
            if original_number in corrected_numbers:
                continue
            if any(edit_distance_is_small(original_number, corrected_number) for corrected_number in corrected_numbers):
                continue
            return False
        return True

    def _strip_outer_punctuation(self, value: str) -> str:
        return re.sub(r"[\s\"'`«».,;:!?]+", "", value or "").lower()

    def _state_address_to_components(self, state: Dict[str, Any]) -> Dict[str, Any]:
        address = state.get("address_input") or {}
        return {
            "region": address.get("region"),
            "city": address.get("city"),
            "street": address.get("street"),
            "house_number": address.get("house"),
            "apartment_number": address.get("flat"),
        }

    def _should_try_correction(self, text: str, validation: Dict[str, Any], components: Dict[str, Any]) -> bool:
        if len(text or "") < 5:
            return False
        if validation.get("match_status") != "not_found":
            return False
        if not components.get("street") or not components.get("house_number"):
            return False
        if validation.get("street_fias_guid"):
            return False
        reason = (validation.get("reason") or "").lower()
        return "улица не найдена" in reason or ("фиас" in reason and "улиц" in reason)

    def _should_try_syntax_correction(self, validation: Dict[str, Any], components: Dict[str, Any]) -> bool:
        status = validation.get("match_status")
        if status != "not_found":
            return False
        return bool(
            components.get("city")
            and components.get("street")
            and components.get("house_number")
        )

    def _syntax_correction_is_safe(
        self,
        *,
        original: Dict[str, Any],
        corrected: Dict[str, Any],
        correction: Dict[str, Any],
    ) -> bool:
        if to_float(correction.get("confidence")) < 0.70:
            return False

        changed_fields = []
        for key in ("city", "street", "house_number"):
            old = original.get(key)
            new = corrected.get(key)
            if self._normalized_for_compare(old) != self._normalized_for_compare(new):
                changed_fields.append(key)
                if correction.get("local_candidate") and key in {"city", "street"}:
                    continue
                if old in (None, "") and new not in (None, "") and key in {"city", "street"}:
                    continue
                if old in (None, "") or new in (None, ""):
                    return False
                if key == "house_number":
                    if not self._house_values_are_compatible(str(old), str(new)):
                        return False
                    continue
                if self._address_part_similarity(str(old), str(new)) < 0.58:
                    return False
        return bool(changed_fields)

    def _address_part_similarity(self, left: str, right: str) -> float:
        left_norm = self._normalized_for_compare(left)
        right_norm = self._normalized_for_compare(right)
        if not left_norm or not right_norm:
            return 0.0
        if left_norm == right_norm:
            return 1.0
        return SequenceMatcher(None, left_norm, right_norm).ratio()

    def _house_values_are_compatible(self, left: str, right: str) -> bool:
        left_norm = self._normalized_for_compare(left)
        right_norm = self._normalized_for_compare(right)
        if left_norm == right_norm:
            return True
        left_numbers = re.findall(r"\d+", left_norm)
        right_numbers = re.findall(r"\d+", right_norm)
        if left_numbers and right_numbers and left_numbers != right_numbers:
            return False
        if left_numbers and right_numbers and left_numbers == right_numbers:
            left_suffix = re.sub(r"\d+", "", left_norm)
            right_suffix = re.sub(r"\d+", "", right_norm)
            return (
                not left_suffix
                or not right_suffix
                or left_suffix.startswith(right_suffix)
                or right_suffix.startswith(left_suffix)
                or SequenceMatcher(None, left_suffix, right_suffix).ratio() >= 0.60
            )
        return SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.75

    def _normalized_for_compare(self, value: Any) -> str:
        text = str(value or "").lower().replace("ё", "е")
        text = re.sub(r"\b(?:город|г|улица|ул|дом|д)\b", "", text)
        text = re.sub(r"[^a-zа-я0-9]+", "", text)
        return text

    def _correction_source(self, text: str, components: Dict[str, Any]) -> str:
        full_address = build_full_address(components)
        return full_address or (text or "")

    def _normalize_spoken_number_slot(self, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        ones = {
            "ноль": 0,
            "один": 1,
            "одна": 1,
            "одно": 1,
            "два": 2,
            "две": 2,
            "три": 3,
            "четыре": 4,
            "пять": 5,
            "шесть": 6,
            "семь": 7,
            "восемь": 8,
            "девять": 9,
        }
        teens = {
            "десять": 10,
            "одиннадцать": 11,
            "двенадцать": 12,
            "тринадцать": 13,
            "четырнадцать": 14,
            "пятнадцать": 15,
            "шестнадцать": 16,
            "семнадцать": 17,
            "восемнадцать": 18,
            "девятнадцать": 19,
        }
        tens = {
            "двадцать": 20,
            "тридцать": 30,
            "сорок": 40,
            "пятьдесят": 50,
            "шестьдесят": 60,
            "семьдесят": 70,
            "восемьдесят": 80,
            "девяносто": 90,
        }
        hundreds = {
            "сто": 100,
            "двести": 200,
            "триста": 300,
            "четыреста": 400,
            "пятьсот": 500,
            "шестьсот": 600,
            "семьсот": 700,
            "восемьсот": 800,
            "девятьсот": 900,
        }
        number_words = set(ones) | set(teens) | set(tens) | set(hundreds)
        tokens = re.findall(r"\d+|[а-яёa-z]+|[/\\-]", text.lower().replace("ё", "е"), flags=re.IGNORECASE)
        if not any(token in number_words for token in tokens):
            return text

        output = []
        current_number = 0
        in_number = False

        def flush_number():
            nonlocal current_number, in_number
            if in_number:
                output.append(str(current_number))
                current_number = 0
                in_number = False

        for token in tokens:
            if token in hundreds:
                current_number += hundreds[token]
                in_number = True
            elif token in tens:
                current_number += tens[token]
                in_number = True
            elif token in teens:
                current_number += teens[token]
                in_number = True
            elif token in ones:
                current_number += ones[token]
                in_number = True
            elif token in {"дробь", "через"}:
                flush_number()
                output.append("/")
            else:
                flush_number()
                output.append(token)

        flush_number()
        normalized = " ".join(output)
        normalized = normalized.replace(" / ", "/").replace(" - ", "-")
        return normalized.strip()

    async def _update_state(
        self,
        state: Dict[str, Any],
        components: Dict[str, Any],
        validation: Dict[str, Any],
        fias_log_ids,
        corrected_text: Optional[str],
    ) -> None:
        address = state.setdefault("address_input", {})

        raw_text = components.get("raw_text") or ""
        if (
            raw_text
            and components.get("_current_message_has_address")
            and raw_text not in (address.get("raw_text") or "")
        ):
            address["raw_text"] = " ".join(part for part in [address.get("raw_text"), raw_text] if part).strip()
        if validation.get("address_full"):
            address["normalized_text"] = validation.get("address_full")
        for key, value in {
            "region": components.get("region"),
            "city": components.get("city"),
            "street": components.get("street"),
            "house": components.get("house_number"),
            "flat": components.get("apartment_number"),
        }.items():
            if value not in (None, ""):
                address[key] = value
        if corrected_text:
            address["corrected_text"] = corrected_text

        state.setdefault("fias_result", {}).update(
            {
                "status": validation.get("match_status"),
                "normalized_address": validation.get("address_full"),
                "fias_street_guid": validation.get("street_fias_guid"),
                "fias_house_guid": validation.get("fias_object_guid"),
                "fias_log_id": fias_log_ids[-1] if fias_log_ids else None,
                "fias_log_ids": fias_log_ids,
                "last_validation_reason": validation.get("reason"),
            }
        )
        state.setdefault("local_address", {}).update(
            {
                "building_id": validation.get("building_id"),
                "unit_id": validation.get("unit_id"),
                "match_source": validation.get("source"),
                "match_confidence": validation.get("confidence") or 0,
                "house_number_normalized": validation.get("house_number"),
            }
        )

        company, resolution_source, service_period_id = await sync_to_async(self.company_resolver.resolve)(
            service_object_id=validation.get("service_object_id")
        )
        service_status = validation.get("match_status")
        if validation.get("service_object_id") and company is None:
            service_status = "not_serviced"
        elif validation.get("service_object_id") and company is not None:
            service_status = "serviced"

        state.setdefault("service_context", {}).update(
            {
                "service_object_id": validation.get("service_object_id"),
                "company_id": company.id if company else None,
                "service_period_id": service_period_id,
                "service_status": service_status,
                "service_status_reason": resolution_source,
            }
        )

    def _missing_address_parts(self, address: Dict[str, Any]):
        missing = []
        if not address.get("city"):
            missing.append("населенный пункт")
        if not address.get("street"):
            missing.append("улица")
        if not address.get("house"):
            missing.append("номер дома")
        return missing

    def _polish_followup_message(
        self,
        *,
        message: str,
        state: Dict[str, Any],
        address_result: Dict[str, Any],
    ) -> Optional[str]:
        if not message:
            return None
        if address_result.get("status") not in {"incomplete", "not_found"}:
            return message
        address = state.get("address_input") or {}
        missing = self._missing_address_parts(address)
        txt_prb = ((state.get("problem") or {}).get("txtPrb") or "").strip()
        if len(missing) == 3:
            if txt_prb:
                return "Детали проблемы зафиксировала. По какому адресу хотите оставить обращение?"
            return "По какому адресу хотите оставить обращение?"
        if len(missing) == 2:
            return f"Уточните {self._join_missing_address_parts(missing)}."
        if len(missing) != 1:
            return message
        return {
            "населенный пункт": "Уточните населенный пункт.",
            "улица": "Уточните улицу.",
            "номер дома": "Уточните номер дома.",
        }.get(missing[0], message)

    def _join_missing_address_parts(self, missing: list) -> str:
        if not missing:
            return "адрес"
        if len(missing) == 1:
            return missing[0]
        return f"{', '.join(missing[:-1])} и {missing[-1]}"

    def _address_question(self, validation: Dict[str, Any]) -> str:
        reason = validation.get("reason") or ""
        if validation.get("match_status") == "not_found":
            return "Не нашла такой дом. Уточните адрес еще раз."
        if "населенный пункт" in reason and "улиц" not in reason and "дом" not in reason:
            return "Уточните населенный пункт."
        if "дом" in reason and "улиц" not in reason:
            return "Уточните номер дома."
        if "улиц" in reason and "дом" not in reason:
            return "Уточните улицу."
        if reason:
            return f"{reason}. Уточните недостающую часть адреса."
        return "По какому адресу хотите оставить обращение?"
