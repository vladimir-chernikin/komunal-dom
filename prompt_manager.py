#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Менеджер промптов для бота УК "Аспект"
Интеграция с БД для динамического управления промптами
"""

import logging
import sys
import os

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from portal.models import AIPrompt

logger = logging.getLogger(__name__)


class PromptManager:
    """Менеджер промптов для бота"""

    def __init__(self):
        self._cache = {}
        self._load_prompts()

    def _load_prompts(self):
        """Загрузка всех активных промптов в кэш"""
        try:
            prompts = AIPrompt.objects.filter(is_active=True)
            self._cache = {p.prompt_id: p.content for p in prompts}
            logger.info(f"Загружено {len(self._cache)} промптов")
        except Exception as e:
            logger.error(f"Ошибка загрузки промптов: {e}")
            self._cache = {}

    def get_prompt(self, prompt_id: str, fallback: str = None) -> str:
        """Получить промпт по ID с запасным вариантом"""
        prompt = self._cache.get(prompt_id)
        if not prompt and fallback:
            logger.warning(f"Промпт {prompt_id} не найден, используем fallback")
            return fallback
        return prompt or ""

    def format_prompt(self, prompt_id: str, **kwargs) -> str:
        """Форматировать промпт с параметрами"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return ""

        try:
            return prompt.format(**kwargs)
        except KeyError as e:
            logger.error(f"Ошибка форматирования промпта {prompt_id}: {e}")
            return prompt

    def get_system_prompt(self) -> str:
        """Получить основной системный промпт"""
        return self.get_prompt('system_main_v2',
            "Ты - дружелюбный помощник УК 'Аспект'. Помогай жителям решать проблемы.")

    def get_greeting_prompt(self, user_name: str = None) -> str:
        """Получить приветствие"""
        greeting = self.get_prompt('greeting_friendly_v2')
        if user_name:
            greeting = greeting.replace("Добрый день!", f"Добрый день, {user_name}!")
        return greeting

    def get_service_detection_rules(self) -> str:
        """Получить правила определения услуг"""
        return self.get_prompt('service_detection_v2',
            "Проанализируй сообщение и определи тип проблемы.")

    def get_address_extraction_rules(self) -> str:
        """Получить правила извлечения адреса"""
        return self.get_prompt('address_extraction_v2',
            "Найди адрес в сообщении.")

    def get_clarification_template(self) -> str:
        """Получить шаблон для запроса уточнения"""
        return self.get_prompt('clarification_needed_v2',
            "Нужно больше информации для помощи.")

    def get_confirmation_template(self) -> str:
        """Получить шаблон подтверждения заявки"""
        return self.get_prompt('confirmation_v2',
            "Подтвердите информацию о заявке.")

    def get_emergency_rules(self) -> str:
        """Получить правила для аварийных ситуаций"""
        return self.get_prompt('emergency_handling_v2',
            "Обработка аварийных ситуаций.")

    def reload(self):
        """Перезагрузить промпты из БД"""
        self._load_prompts()
        logger.info("Промпты перезагружены")

    @staticmethod
    def format_clarification_message(user_message: str, prompt_template: str) -> str:
        """Форматировать сообщение с запросом уточнения"""
        # Экранируем кавычки в сообщении пользователя
        safe_message = user_message.replace('"', '\\"')

        return prompt_template.format(user_message=safe_message)


# Глобальный экземпляр менеджера промптов
prompt_manager = PromptManager()