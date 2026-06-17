#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TagSearchService - микросервис поиска услуг по тегам
⚠️  ЗАКОММЕНТИРОВАН (2026-03-25): ref_tags и service_tags удалены

ИСХОДНЫЙ КОД (перенесен в old/):
- Использует триграммные индексы (pg_trgm) + pymorphy2 + rapidfuzz
- Ищет ТОЛЬКО ПО ТЕГАМ из ref_tags
- Кэш тегов в памяти (~50KB RAM)
- LRU cache для pymorphy2 лемматизации
- rapidfuzz только для слов >= 6 букв
- Batch SQL запросы вместо циклов

ПРИЧИНА ОТКЛЮЧЕНИЯ:
- ref_tags удален (655 тегов)
- service_tags удален (416 связей услуга-тег)
- Теги не используются в новом catalog

ЗАМЕНА:
- Временное решение: этот класс отключен
- TODO: Если теги нужны в будущем - пересоздать ref_tags для нового catalog
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class TagSearchService:
    """
    ⚠️  ОТКЛЮЧЕН (2026-03-25): ref_tags и service_tags удалены

    Пустой класс-заглушка для совместимости с существующим кодом.
    Возвращает пустые результаты.
    """

    def __init__(self):
        self.morph = None
        self._stopwords = None
        logger.warning("TagSearchService ОТКЛЮЧЕН: ref_tags и service_tags удалены")

    async def search_services_by_tags(self, query: str, **kwargs) -> List[Dict]:
        """
        Пустой метод (возвращает пустой список)

        Args:
            query: Текстовый запрос
            **kwargs: Дополнительные параметры (игнорируются)

        Returns:
            Пустой список []
        """
        logger.warning(f"TagSearchService.search_services_by_tags() вызван, но отключен. Query: '{query[:50]}...'")
        return []

    async def get_tags_for_service(self, service_id: int) -> List[str]:
        """Пустой метод (возвращает пустой список)"""
        logger.warning(f"TagSearchService.get_tags_for_service() вызван, но отключен. ID: {service_id}")
        return []

    # Другие методы класса закомментированы (см. старую версию в old/)
