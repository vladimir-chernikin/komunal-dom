#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VectorSearchService - микросервис поиска услуг с триграммным индексом
Использует pg_trgm для нечеткого поиска по scenario_name (БЕЗ description)

ИСПРАВЛЕНО (2026-01-13):
- Удален поиск по description_for_search (избыточное поле)
"""

import logging
import re
from typing import List, Dict, Any
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Микросервис поиска услуг с триграммным индексом pg_trgm"""

    def __init__(self):
        # ИСПРАВЛЕНО (2026-01-13): УБРАНО кэширование для избежания проблем с памятью и параллельными запросами
        # ИСПРАВЛЕНО (2026-01-13): Удален _load_services() - поиск идет прямым SQL с фильтрами
        logger.info("VectorSearchService инициализирован (прямой SQL с pg_trgm)")

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Поиск услуг с триграммным поиском через pg_trgm
        Фильтрация идет в SQL WHERE, Python фильтрация УБРАНА

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для SQL WHERE
                     {'incident_type': 'Инцидент', 'location_type': 'Индивидуальное', 'category': 'Водоснабжение'}

        Returns:
            Dict: Результат поиска в формате JSON {[КодУслуги], [Релевантность]}

        ИСПРАВЛЕНО (2026-01-13):
        - Убран _load_services() - поиск прямым SQL
        - Фильтрация перенесена в SQL WHERE
        - Убрана избыточная Python фильтрация
        """
        try:
            logger.info(f"VectorSearch: поиск по тексту '{message_text[:50]}...'")

            # Нормализуем текст сообщения
            message_clean = re.sub(r'[^\w\s]', ' ', message_text.lower())
            message_clean = re.sub(r'\s+', ' ', message_clean).strip()

            # Helper функция для извлечения значения из фильтра
            def get_filter_value(filter_key):
                """Извлекает value из фильтра, который может быть строкой или dict {'value': ..., 'confidence': ...}"""
                filter_data = filters.get(filter_key) if filters else None
                if filter_data is None:
                    return None
                if isinstance(filter_data, dict):
                    return filter_data.get('value')
                return filter_data

            # Извлекаем фильтры для SQL WHERE
            incident_type = get_filter_value('incident_type') or ''
            location_type = get_filter_value('location_type') or ''
            category = get_filter_value('category') or ''

            # ИСПРАВЛЕНО (2026-01-13): Используем pg_trgm с фильтрами в SQL WHERE
            candidates = await self._search_with_pg_trgm(message_clean, incident_type, location_type, category)

            result = {
                'status': 'success',
                'candidates': candidates,
                'method': 'vector_search'
            }

            logger.info(f"VectorSearch: найдено услуг: {len(candidates)}")
            return result

        except Exception as e:
            logger.error(f"Ошибка в VectorSearchService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }

    def _calculate_adaptive_threshold(self, message_text: str) -> tuple:
        """
        Адаптивный расчет порога и лимита в зависимости от длины запроса

        ИСПРАВЛЕНО (2025-12-25): Адаптивный порог вместо фиксированного 0.2

        Args:
            message_text: Текст сообщения

        Returns:
            tuple: (threshold, limit) - порог похожести и лимит результатов
        """
        # Считаем количество слов
        words = message_text.strip().split()
        word_count = len(words)

        # Считаем количество символов
        char_count = len(message_text.strip())

        # Определяем категорию запроса
        if word_count <= 2 and char_count < 15:
            # Короткий запрос: "у меня течет", "сломался"
            threshold = 0.12
            limit = 5
            category = "короткий"
        elif word_count <= 5 and char_count < 40:
            # Средний запрос: "у меня прорвало трубу в ванной"
            threshold = 0.18
            limit = 7
            category = "средний"
        else:
            # Длинный запрос: подробное описание проблемы
            threshold = 0.25
            limit = 10
            category = "длинный"

        logger.info(
            f"VectorSearch: запрос '{message_text[:30]}...' -> "
            f"категория='{category}' (слов:{word_count}, символов:{char_count}), "
            f"порог={threshold}, лимит={limit}"
        )

        return threshold, limit

    async def _search_with_pg_trgm(self, message_text: str, incident_type: str = '', location_type: str = '', category: str = '') -> List[Dict]:
        """
        Поиск с использованием pg_trgm через SQL
        Фильтрация идет в SQL WHERE (incident_type, location_type, category)

        ИСПРАВЛЕНО (2026-01-13):
        - Добавлены фильтры в SQL WHERE
        - Убрана избыточная Python фильтрация
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # Вычисляем адаптивный порог и лимит
                    threshold, limit = self._calculate_adaptive_threshold(message_text)

                    # ИСПРАВЛЕНО (2026-01-13): Добавлены фильтры в SQL WHERE
                    # Для очень коротких запросов (< 5 букв) используем ILIKE
                    if len(message_text.strip()) < 5:
                        cursor.execute("""
                            SELECT
                                sc.service_id,
                                sc.scenario_name as service_name,
                                COALESCE(rst.type_name, '') as incident_type,
                                COALESCE(rc.category_name, '') as category,
                                COALESCE(rl.localization_name, '') as location_type,
                                0.5 as similarity
                            FROM services_catalog sc
                            LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                            LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                            LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                            WHERE sc.is_active = TRUE
                              AND (sc.scenario_name ILIKE %s)
                              AND (%s = '' OR rst.type_name = %s)
                              AND (%s = '' OR rl.localization_name = %s)
                              AND (%s = '' OR rc.category_name = %s)
                            LIMIT %s
                        """, [f'%{message_text}%', incident_type, incident_type,
                              location_type, location_type, category, category, limit])
                    else:
                        # Для остальных запросов используем word_similarity с адаптивным порогом
                        # ИСПРАВЛЕНО (2026-01-13): Добавлены фильтры в SQL WHERE
                        cursor.execute("""
                            SELECT
                                sc.service_id,
                                sc.scenario_name as service_name,
                                COALESCE(rst.type_name, '') as incident_type,
                                COALESCE(rc.category_name, '') as category,
                                COALESCE(rl.localization_name, '') as location_type,
                                COALESCE(
                                    word_similarity(%s, sc.scenario_name),
                                    0
                                ) as similarity
                            FROM services_catalog sc
                            LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                            LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                            LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                            WHERE sc.is_active = TRUE
                              AND (word_similarity(%s, sc.scenario_name) > %s)
                              AND (%s = '' OR rst.type_name = %s)
                              AND (%s = '' OR rl.localization_name = %s)
                              AND (%s = '' OR rc.category_name = %s)
                            ORDER BY similarity DESC
                            LIMIT %s
                        """, [message_text, message_text, threshold,
                              incident_type, incident_type, location_type, location_type,
                              category, category, limit])

                    results = cursor.fetchall()

                # Фильтруем по адаптивному порогу и возвращаем ТОП-N
                candidates = []
                for service_id, service_name, incident_type, category, location_type, similarity in results:
                    if similarity >= threshold:  # Используем адаптивный порог
                        candidates.append({
                            'service_id': service_id,
                            'service_name': service_name,
                            'confidence': round(similarity, 3),
                            'source': 'vector_search',
                            'incident_type': incident_type or '',
                            'category': category or '',
                            'location_type': location_type or ''
                        })

                logger.info(f"VectorSearch: найдено {len(candidates)} кандидатов (порог: {threshold})")
                return candidates

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка триграммного поиска: {e}")
            # Фоллбек на простой поиск
            return await self._fallback_search(message_text, incident_type, location_type, category)

    async def _fallback_search(self, message_text: str, incident_type: str = '', location_type: str = '', category: str = '') -> List[Dict]:
        """
        Фоллбек на простой поиск через LIKE
        ИСПРАВЛЕНО (2026-01-13): Добавлены фильтры в SQL WHERE
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-01-13): Добавлены фильтры в SQL WHERE
                    cursor.execute("""
                        SELECT
                            sc.service_id,
                            sc.scenario_name as service_name,
                            COALESCE(rst.type_name, '') as incident_type,
                            COALESCE(rc.category_name, '') as category,
                            COALESCE(rl.localization_name, '') as location_type
                        FROM services_catalog sc
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                          AND (sc.scenario_name ILIKE %s)
                          AND (%s = '' OR rst.type_name = %s)
                          AND (%s = '' OR rl.localization_name = %s)
                          AND (%s = '' OR rc.category_name = %s)
                        LIMIT 10
                    """, [f'%{message_text}%', incident_type, incident_type,
                          location_type, location_type, category, category])

                    results = cursor.fetchall()

                candidates = []
                for service_id, service_name, incident_type, category, location_type in results:
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service_name,
                        'confidence': 0.5,  # Фиксированная уверенность для LIKE поиска
                        'source': 'vector_search_fallback',
                        'incident_type': incident_type or '',
                        'category': category or '',
                        'location_type': location_type or ''
                    })

                return candidates

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка фоллбек поиска: {e}")
            return []
