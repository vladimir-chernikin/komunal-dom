import re
from typing import Dict, Optional

NOISE_PATTERNS = (r"\bроссия\b", r"\b\d{6}\b")
HOUSE_TOKEN_PATTERNS = (
    (r"\bкорпус\b", "к"),
    (r"\bкорп\b", "к"),
    (r"\bстроение\b", "с"),
    (r"\bстр\b", "с"),
    (r"\bлитера\b", "лит"),
    (r"\bдом\b", "д"),
)


def normalize_text(value: Optional[str]) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = text.replace("№", " ")
    text = re.sub(r"[,;]+", ",", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,")


def normalize_house_number(value: Optional[str]) -> str:
    text = normalize_text(value)
    for pattern, replacement in HOUSE_TOKEN_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace(" ", "")
    text = re.sub(r"^д", "", text)
    return text.upper()


def normalize_unit_number(value: Optional[str]) -> str:
    text = normalize_text(value)
    text = re.sub(r"^(кв|квартира|пом|помещение)\.?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(" ", "")
    return text.upper()


def build_full_address(parts: Dict[str, Optional[str]]) -> str:
    city = (parts.get("city") or "").strip()
    street = (parts.get("street") or "").strip()
    house_number = normalize_house_number(parts.get("house_number"))
    chunks = []
    if city:
        chunks.append(f"г {city}")
    if street:
        chunks.append(f"ул {street}")
    if house_number:
        chunks.append(f"д {house_number}")
    return ", ".join(chunks)
