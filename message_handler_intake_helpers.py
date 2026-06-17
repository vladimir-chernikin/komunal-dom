import re
from typing import Dict, Optional


def get_last_bot_metadata_from_history(dialog_history: list) -> Dict:
    for msg in reversed(dialog_history or []):
        if msg.get("role") == "bot":
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict):
                return metadata
    return {}


def format_address(address_components: Dict) -> str:
    parts = []
    if address_components.get("city"):
        parts.append(address_components["city"])
    if address_components.get("street"):
        parts.append(address_components["street"])
    if address_components.get("house_number"):
        parts.append(f"дом {address_components['house_number']}")
    if address_components.get("apartment_number"):
        parts.append(f"кв. {address_components['apartment_number']}")
    return ", ".join(parts)


def build_intake_context(
    *,
    existing_context: Optional[Dict],
    address_components: Dict,
    address_validation: Dict,
) -> Dict:
    context = dict(existing_context or {})
    context["address_components"] = address_components
    context["address_validation"] = address_validation
    context["address_string"] = address_validation.get("address_full") or format_address(address_components)
    if address_validation.get("service_object_id"):
        context["service_object_id"] = address_validation.get("service_object_id")
    if address_validation.get("building_id"):
        context["building_id"] = address_validation.get("building_id")
    if address_validation.get("unit_id"):
        context["unit_id"] = address_validation.get("unit_id")
    return context


def merge_result_metadata(
    result: Dict,
    *,
    address_components: Optional[Dict] = None,
    address_validation: Optional[Dict] = None,
    intake_context: Optional[Dict] = None,
) -> Dict:
    payload = dict(result or {})
    metadata = payload.get("_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if address_components is not None:
        metadata["address_components"] = address_components
    if address_validation is not None:
        metadata["address_validation"] = address_validation
    if intake_context is not None:
        metadata["intake_context"] = intake_context
    payload["_metadata"] = metadata
    return payload


def message_is_address_only(text: str, address_components: Dict) -> bool:
    if not text:
        return False
    if not address_components.get("street") or not address_components.get("house_number"):
        return False

    lowered = text.lower()
    for key in ("city", "street", "house_number", "apartment_number"):
        value = address_components.get(key)
        if value:
            lowered = lowered.replace(str(value).lower(), " ")

    lowered = re.sub(r"(город|г\.|улица|ул\.?|дом|д\.?|квартира|кв\.?|подъезд|подьезд|под\.?)", " ", lowered)
    lowered = re.sub(r"[^а-яёa-z0-9]+", " ", lowered).strip()
    if not lowered:
        return True

    problem_keywords = (
        "теч",
        "засор",
        "слом",
        "не работает",
        "не греет",
        "нет",
        "авар",
        "вода",
        "свет",
        "отоплен",
        "лифт",
    )
    return not any(keyword in lowered for keyword in problem_keywords)
