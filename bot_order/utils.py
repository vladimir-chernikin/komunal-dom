import json
import re
from typing import Any, Dict, Optional


def parse_json_object(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    cleaned = cleaned.translate(
        str.maketrans(
            {
                "“": '"',
                "”": '"',
                "„": '"',
                "«": '"',
                "»": '"',
            }
        )
    )
    try:
        data = json.loads(cleaned)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, result))


def normalize_for_match(value: Optional[str]) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def is_greeting_only(text: str) -> bool:
    words = re.findall(r"[a-zа-яё]+", normalize_for_match(text))
    if not words or len(words) > 4:
        return False
    greetings = {
        "привет",
        "здравствуйте",
        "здравствуй",
        "добрый",
        "день",
        "вечер",
        "утро",
        "здрасте",
        "hello",
        "hi",
    }
    return all(word in greetings for word in words)


def is_affirmative(text: str) -> bool:
    value = normalize_for_match(text).strip(" .,!?:;")
    return value in {
        "да",
        "верно",
        "правильно",
        "точно",
        "подтверждаю",
        "согласен",
        "согласна",
        "оформляйте",
        "оформляй",
        "yes",
        "ok",
        "ок",
    }


def is_negative(text: str) -> bool:
    value = normalize_for_match(text).strip(" .,!?:;")
    return value in {
        "нет",
        "неверно",
        "не правильно",
        "неправильно",
        "не то",
        "ошибка",
        "ошиблись",
        "no",
    }


def safe_truncate(value: Any, limit: int = 4000) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        return {key: safe_truncate(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_truncate(item, limit) for item in value[:50]]
    return value
