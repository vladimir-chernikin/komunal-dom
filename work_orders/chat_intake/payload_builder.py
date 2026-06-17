from typing import Any, Dict, Optional


class ChatIntakePayloadBuilder:
    CHANNEL_MAP = {
        "telegram": "telegram",
        "web": "site_chat",
        "api": "site_chat",
        "test_bot": "manual",
        "transcriber": "phone",
        "whatsapp": "manual",
        "maxchat": "max",
    }

    def build(
        self,
        *,
        service_result: Dict[str, Any],
        intake_context: Dict[str, Any],
        original_text: str,
        channel: str,
        session_id: str,
        user_id: str,
        django_user_id: Optional[int],
        message_log_id: Optional[int],
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata = service_result.get("_metadata") or {}
        filters = metadata.get("established_filters") or {}
        txt_prb = metadata.get("txtPrb") or original_text or ""
        address_validation = intake_context.get("address_validation") or {}
        address_components = intake_context.get("address_components") or {}

        priority_code = self._resolve_priority_code(txt_prb, filters)
        is_emergency = priority_code in {"high", "critical"}

        return {
            "schema_version": "1.1",
            "channel": self.CHANNEL_MAP.get(channel, "site_chat"),
            "session_id": session_id,
            "message_log_ref": str(message_log_id) if message_log_id else None,
            "user": {
                "external_user_id": str(user_id),
                "django_user_id": django_user_id,
                "display_name": self._extract_display_name(source_metadata),
                "phone": self._extract_phone(source_metadata),
            },
            "address": {
                "raw_text": intake_context.get("address_string") or self._format_address(address_components),
                "normalized_text": address_validation.get("address_full")
                or intake_context.get("address_string")
                or self._format_address(address_components),
                "fias_house_guid": address_validation.get("fias_object_guid"),
                "street_fias_guid": address_validation.get("street_fias_guid"),
                "house_number": address_validation.get("house_number"),
                "fias_level_id": address_validation.get("fias_level_id"),
                "building_id": address_validation.get("building_id"),
                "unit_id": address_validation.get("unit_id"),
                "service_object_id": address_validation.get("service_object_id"),
                "match_status": address_validation.get("match_status")
                or ("matched" if address_validation.get("found") else "not_found"),
                "validation_source": address_validation.get("source") or "fias",
                "components": address_components,
            },
            "classification": {
                "incident_type": self._filter_value(filters, "incident_type"),
                "localization": self._filter_value(filters, "location_type"),
                "category": self._filter_value(filters, "category"),
                "service_id": service_result.get("service_id"),
                "service_name": service_result.get("service_name"),
                "confidence": service_result.get("confidence"),
            },
            "problem": {
                "txtPrb": txt_prb,
                "summary": txt_prb or original_text,
                "additional_details": original_text if original_text and original_text != txt_prb else None,
                "is_emergency": is_emergency,
                "priority_code": priority_code,
            },
            "decision": {
                "can_create_work_order": bool(
                    address_validation.get("service_object_id") and service_result.get("service_id")
                ),
                "reason_if_blocked": None,
                "requires_operator": False,
            },
            "meta": {
                "llm_provider": "gigachat",
                "llm_model": None,
                "prompt_versions": {},
                "company_resolution": None,
                "company_service_period_id": None,
                "source_metadata": source_metadata or {},
            },
        }

    def filter_value(self, filters: Dict[str, Any], key: str) -> Optional[str]:
        return self._filter_value(filters, key)

    def format_address(self, components: Dict[str, Any]) -> str:
        return self._format_address(components)

    def compose_additional_info(self, payload: Dict[str, Any]) -> str:
        address = payload.get("address") or {}
        lines = [
            f"Канал: {payload.get('channel')}",
            f"Сессия: {payload.get('session_id')}",
            f"Адрес: {address.get('normalized_text')}",
            f"FIAS GUID дома: {address.get('fias_house_guid')}",
            f"FIAS GUID улицы: {address.get('street_fias_guid')}",
            f"Номер дома: {address.get('house_number')}",
            f"Локальный объект: {address.get('service_object_id')}",
            f"Локальный building_id: {address.get('building_id')}",
        ]
        if address.get("components", {}).get("apartment_number"):
            lines.append(f"Квартира из текста: {address['components']['apartment_number']}")
        return "\n".join(lines)

    def _filter_value(self, filters: Dict[str, Any], key: str) -> Optional[str]:
        item = filters.get(key) or {}
        return item.get("value") if isinstance(item, dict) else None

    def _resolve_priority_code(self, txt_prb: str, filters: Dict[str, Any]) -> str:
        text = (txt_prb or "").lower()
        if any(keyword in text for keyword in ["газ", "пожар", "горит", "взрыв"]):
            return "critical"
        if any(keyword in text for keyword in ["протеч", "затоп", "искрит", "нет света", "нет воды", "течет"]):
            return "high"
        incident = (self._filter_value(filters, "incident_type") or "").lower()
        if "инцидент" in incident:
            return "high"
        return "normal"

    def _format_address(self, components: Dict[str, Any]) -> str:
        parts = []
        if components.get("region"):
            parts.append(components["region"])
        if components.get("city"):
            parts.append(components["city"])
        if components.get("street"):
            parts.append(f"ул. {components['street']}")
        if components.get("house_number"):
            parts.append(f"д. {components['house_number']}")
        if components.get("apartment_number"):
            parts.append(f"кв. {components['apartment_number']}")
        return ", ".join(parts)

    def _extract_display_name(self, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        metadata = metadata or {}
        telegram_info = metadata.get("telegram_info") or {}
        for candidate in [
            telegram_info.get("username"),
            telegram_info.get("first_name"),
            metadata.get("username"),
            metadata.get("first_name"),
        ]:
            if candidate:
                return str(candidate)
        return None

    def _extract_phone(self, metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        metadata = metadata or {}
        api_info = metadata.get("api_info") or {}
        phone = api_info.get("nomer")
        return str(phone) if phone else None
