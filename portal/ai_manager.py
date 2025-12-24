"""
Менеджер AI промптов для Telegram бота
"""
import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from portal.models import AIPrompt


class AIManager:
    """Управление AI промптами и ответами бота"""

    def __init__(self):
        self.prompts_cache = {}
        self.load_prompts()

    def load_prompts(self):
        """Загружает все активные промпты в кэш"""
        try:
            active_prompts = AIPrompt.objects.filter(is_active=True)
            self.prompts_cache = {p.prompt_id: p.content for p in active_prompts}
            print(f"Загружено {len(self.prompts_cache)} промптов")
        except Exception as e:
            print(f"Ошибка загрузки промптов: {e}")
            self.prompts_cache = {}

    def get_prompt(self, prompt_id, default=""):
        """Получить промпт по ID"""
        return self.prompts_cache.get(prompt_id, default)

    def format_address_response(self, address, found, building_info="", additional_info=""):
        """Формирует ответ для проверки адреса"""
        template = self.get_prompt('address_check_template')
        if not template:
            # Формируем базовый ответ если шаблон не найден
            if found:
                return f"✅ Адрес '{address}' найден в зоне обслуживания УК 'Аспект'{building_info}"
            else:
                return f"❌ Адрес '{address}' не входит в зону обслуживания УК 'Аспект'"

        # Заменяем переменные в шаблоне
        response = template.format(
            address=address,
            if_found="{if_found}" if found else "",
            endif="{endif}" if found else "",
            building_info=building_info,
            additional_info=additional_info
        )

        # Очищаем служебные теги
        response = response.replace("{if_found}", "").replace("{endif}", "").replace("{else}", "")

        return response

    def get_greeting_message(self):
        """Получить приветственное сообщение"""
        return self.get_prompt('greeting_main',
            "Здравствуйте! Я помощник УК 'Аспект'. Отправьте мне ваш адрес для проверки.")

    def get_address_not_found_message(self, address):
        """Получить сообщение о ненайденном адресе"""
        template = self.get_prompt('address_not_found')
        if template:
            return template
        return f"К сожалению, адрес '{address}' не найден в нашей базе данных зоны обслуживания."

    def get_farewell_message(self):
        """Получить прощальное сообщение"""
        return self.get_prompt('farewell_main',
            "Благодарю за обращение! С уважением, УК 'Аспект'")

    def get_error_message(self):
        """Получить сообщение об ошибке"""
        return self.get_prompt('error_handling',
            "Произошла техническая неполадка. Пожалуйста, повторите запрос позже.")

    def get_profanity_warning(self):
        """Получить предупреждение о ругательствах"""
        return self.get_prompt('profanity_warning',
            "Прошу вас быть вежливым в общении.")

    def get_default_response(self):
        """Получить ответ по умолчанию"""
        return self.get_prompt('default_response',
            "Я Сигизмунд Лазоревич, помощник УК 'Аспект'. Отправьте мне ваш адрес для проверки.")

    def get_system_prompt(self):
        """Получить системный промпт для AI"""
        return self.get_prompt('system_main',
            "Ты - вежливый помощник управляющей компании 'Аспект'. Проверяешь адреса и консультируешь клиентов.")

    def reload_prompts(self):
        """Перезагрузить промпты из базы данных"""
        self.load_prompts()


# Глобальный экземпляр менеджера
ai_manager = AIManager()