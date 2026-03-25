#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VectorSearchService - микросервис векторного поиска услуг
⚠️  ЗАКОММЕНТИРОВАН (2026-03-25): Старый catalog удален, embeddings недоступны

ИСХОДНЫЙ КОД (перенесен в old/):
- Использует Yandex Embeddings API для семантического поиска
- Двойной поиск: по embedding тегов (точность) + embedding услуг (полнота)
- Фильтрация в SQL WHERE (incident_type, location_type, category)
- Слияние результатов с адаптивными весами
- Кэш embeddings в памяти (~70KB)
- NumPy vectorized cosine similarity
- Batch загрузка вместо множества SQL запросов

ПРИЧИНА ОТКЛЮЧЕНИЯ:
- Старый catalog (78 услуг с embeddings) заменен на новый (44 услуги без embeddings)
- ref_tags удален (655 тегов)
- service_tags удален (416 связей)
- ref_tags_embeddings удален

ЗАМЕНА:
- Временное решение: этот класс отключен
- TODO: Создать новый скрипт генерации embeddings для нового catalog
- TODO: Пересчитать embeddings для 44 услуг
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    ⚠️  ОТКЛЮЧЕН (2026-03-25): Старый catalog удален, embeddings недоступны

    Пустой класс-заглушка для совместимости с существующим кодом.
    Возвращает пустые результаты.
    """

    def __init__(self):
        logger.warning("VectorSearchService ОТКЛЮЧЕН: старый catalog удален, embeddings недоступны")

    async def search_services(self, query: str, **kwargs) -> List[Dict]:
        """
        Пустой метод (возвращает пустой список)

        Args:
            query: Текстовый запрос
            **kwargs: Дополнительные параметры (игнорируются)

        Returns:
            Пустой список []
        """
        logger.warning(f"VectorSearchService.search_services() вызван, но отключен. Query: '{query[:50]}...'")
        return []

    async def get_service_by_id(self, service_id: int) -> Dict:
        """Пустой метод (возвращает None)"""
        logger.warning(f"VectorSearchService.get_service_by_id() вызван, но отключен. ID: {service_id}")
        return None

    # Другие методы класса закомментированы (см. старую версию в old/)
