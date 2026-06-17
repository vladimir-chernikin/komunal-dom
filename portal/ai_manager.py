"""
Legacy compatibility layer for the old enhanced Telegram bot.

This module no longer reads prompts from the deleted AIPrompt table.
Only minimal hardcoded fallback copy remains here.
"""

HARD_FALLBACK_PREFIX = "¤"

LEGACY_SYSTEM_PROMPT = (
    "Ты - вежливый помощник управляющей компании 'Аспект'. "
    "Проверяешь адреса и кратко консультируешь клиентов."
)


def _hardcoded(text):
    return f"{HARD_FALLBACK_PREFIX} {text}"


class AIManager:
    """Compatibility wrapper without database-backed prompts."""

    def load_prompts(self):
        return None

    def get_prompt(self, prompt_id, default=""):
        return default

    def format_address_response(self, address, found, building_info="", additional_info=""):
        if found:
            return _hardcoded(
                f"Адрес '{address}' найден в зоне обслуживания УК 'Аспект'{building_info}"
            )
        return _hardcoded(
            f"Адрес '{address}' не входит в зону обслуживания УК 'Аспект'."
        )

    def get_greeting_message(self):
        return _hardcoded(
            "Здравствуйте. Я помощник УК 'Аспект'. Отправьте адрес для проверки."
        )

    def get_address_not_found_message(self, address):
        return _hardcoded(
            f"Адрес '{address}' не найден в базе зоны обслуживания."
        )

    def get_farewell_message(self):
        return _hardcoded("Благодарю за обращение.")

    def get_error_message(self):
        return _hardcoded(
            "Произошла техническая ошибка. Повторите запрос позже."
        )

    def get_profanity_warning(self):
        return _hardcoded("Пожалуйста, соблюдайте корректный тон общения.")

    def get_default_response(self):
        return _hardcoded(
            "Опишите проблему или отправьте адрес для проверки."
        )

    def get_system_prompt(self):
        return LEGACY_SYSTEM_PROMPT

    def reload_prompts(self):
        return None


ai_manager = AIManager()
