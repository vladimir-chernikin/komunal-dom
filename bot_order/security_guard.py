from typing import Dict

from .utils import normalize_for_match


class SecurityGuard:
    """Fast deterministic guard for prompt/security exfiltration attempts."""

    BLOCK_PATTERNS = {
        "prompt_exfiltration": [
            "покажи промпт",
            "системный промпт",
            "system prompt",
            "developer message",
            "забудь инструкции",
            "ignore instructions",
            "раскрой инструкции",
        ],
        "secret_exfiltration": [
            "покажи токен",
            "api key",
            "пароль",
            ".env",
            "секретный ключ",
            "master-token",
        ],
        "personal_data": [
            "телефоны жильцов",
            "чужая заявка",
            "персональные данные",
            "список жильцов",
            "все адреса жильцов",
        ],
    }

    def check(self, text: str) -> Dict:
        value = normalize_for_match(text)
        for risk_code, patterns in self.BLOCK_PATTERNS.items():
            if any(pattern in value for pattern in patterns):
                return {
                    "allowed": False,
                    "risk_code": risk_code,
                    "safe_reply": "Я помогу оформить заявку по дому. Для начала определим адрес, где обнаружена проблема.",
                    "continue_order_flow": False,
                }
        return {
            "allowed": True,
            "risk_code": None,
            "safe_reply": None,
            "continue_order_flow": True,
        }
