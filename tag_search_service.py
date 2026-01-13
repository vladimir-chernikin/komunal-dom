#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TagSearchService - микросервис поиска услуг по тегам
Использует триграммные индексы (pg_trgm) для поиска по тегам
Ищет ТОЛЬКО ПО ТЕГАМ из ref_tags
"""

import logging
import re
from typing import List, Dict
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class TagSearchService:
    """Микросервис поиска услуг по тегам с использованием pg_trgm"""

    def __init__(self):
        self.service_cache = None
        logger.info("TagSearchService инициализирован (поиск по ТЕГАМ)")

    async def _load_services(self, filters: Dict = None):
        """
        Асинхронная загрузка услуг из БД в кэш

        ИСПРАВЛЕНО (2026-01-13):
        - Добавлена предварительная фильтрация по filters (только confidence >= 90%)
        """
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Строим SQL запрос с фильтрами для предварительной фильтрации
                    sql = """
                        SELECT sc.service_id, sc.scenario_name,
                               COALESCE(rc.category_name, '') as category,
                               COALESCE(ro.object_name, '') as object_name,
                               COALESCE(rst.type_name, '') as incident_type,
                               COALESCE(rl.localization_name, '') as location_type
                        FROM services_catalog sc
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                    """
                    params = []

                    # Предварительная фильтрация по category (confidence >= 90%)
                    if filters:
                        category_data = filters.get('category')
                        if category_data and isinstance(category_data, dict):
                            category_conf = category_data.get('confidence', 0)
                            if category_conf >= 0.9:
                                sql += " AND rc.category_name = %s"
                                params.append(category_data.get('value'))

                        # Предварительная фильтрация по object (confidence >= 90%)
                        object_data = filters.get('object')
                        if object_data and isinstance(object_data, dict):
                            object_conf = object_data.get('confidence', 0)
                            if object_conf >= 0.9:
                                sql += " AND ro.object_name = %s"
                                params.append(object_data.get('value'))

                        # Предварительная фильтрация по incident_type (confidence >= 90%)
                        incident_data = filters.get('incident_type')
                        if incident_data and isinstance(incident_data, dict):
                            incident_conf = incident_data.get('confidence', 0)
                            if incident_conf >= 0.9:
                                sql += " AND rst.type_name = %s"
                                params.append(incident_data.get('value'))

                        # Предварительная фильтрация по location_type (confidence >= 90%)
                        location_data = filters.get('location_type')
                        if location_data and isinstance(location_data, dict):
                            location_conf = location_data.get('confidence', 0)
                            if location_conf >= 0.9:
                                sql += " AND rl.localization_name = %s"
                                params.append(location_data.get('value'))

                    sql += " ORDER BY sc.service_id"

                    cursor.execute(sql, params)
                    services = cursor.fetchall()

                    service_cache = {}
                    for row in services:
                        service_id = row[0]
                        scenario_name = row[1]
                        category = row[2]
                        object_name = row[3]
                        incident_type = row[4]
                        location_type = row[5]

                        service_cache[service_id] = {
                            'service_id': service_id,
                            'service_name': scenario_name,
                            'category': category,
                            'object_name': object_name,
                            'incident_type': incident_type,
                            'location_type': location_type
                        }
                    return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"TagSearchService: загружено {len(self.service_cache)} услуг")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = {}

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод поиска услуги по тексту сообщения
        Ищет ТОЛЬКО ПО ТЕГАМ с использованием триграммных индексов (pg_trgm)

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для предварительной фильтрации в SQL

        Returns:
            Dict: Результат поиска в формате JSON {status, candidates: [{...}]}

        ИСПРАВЛЕНО (2026-01-13):
        - Использует pg_trgm (word_similarity) для поиска по тегам
        - Ищет только по тегам (scenario_name и description НЕ участвуют)
        """
        try:
            # Предварительная фильтрация через загрузку услуг
            if not self.service_cache:
                await self._load_services(filters)

            if not self.service_cache:
                return {"status": "error", "message": "Нет загруженных услуг", "candidates": []}

            # Предобработка текста
            clean_text = self._preprocess_text(message_text)

            logger.info(f"TagSearchService: поиск по тексту '{clean_text}' (поиск по ТЕГАМ)")

            # Поиск с помощью триграммного индекса
            candidates = await self._search_with_trgm(clean_text)

            if candidates:
                return {
                    "status": "success",
                    "candidates": candidates,
                    "method": "tag_search"
                }
            else:
                return {
                    "status": "not_found",
                    "candidates": [],
                    "method": "tag_search"
                }

        except Exception as e:
            logger.error(f"Ошибка в TagSearchService.search: {e}")
            return {
                "status": "error",
                "message": f"Ошибка поиска: {str(e)}",
                "candidates": []
            }

    async def _search_with_trgm(self, message_text: str) -> List[Dict]:
        """
        Поиск услуг с помощью триграммного индекса (pg_trgm)
        Ищет только по тегам из ref_tags

        ИСПРАВЛЕНО (2026-01-13): Использует word_similarity для поиска по тегам
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-01-13): Ищем только по тегам с триграммным поиском
                    cursor.execute("""
                        SELECT DISTINCT sc.service_id, sc.scenario_name,
                               COALESCE(rc.category_name, '') as category,
                               COALESCE(ro.object_name, '') as object_name,
                               COALESCE(rst.type_name, '') as incident_type,
                               COALESCE(rl.localization_name, '') as location_type,
                               MAX(word_similarity(%s, rt.tag_name)) as similarity
                        FROM services_catalog sc
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        LEFT JOIN service_tags st ON sc.service_id = st.service_id
                        LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id AND rt.is_active = TRUE
                        WHERE sc.is_active = TRUE
                          AND word_similarity(%s, rt.tag_name) > 0.3
                        GROUP BY sc.service_id, sc.scenario_name, rc.category_name, ro.object_name, rst.type_name, rl.localization_name
                        ORDER BY similarity DESC
                    """, [message_text, message_text])

                    results = cursor.fetchall()

                    # Формируем кандидатов
                    candidates = []

                    for row in results:
                        service_id = row[0]
                        scenario_name = row[1]
                        category = row[2]
                        object_name = row[3]
                        incident_type = row[4]
                        location_type = row[5]
                        similarity = row[6]

                        # Confidence = similarity (от 0.3 до 1.0)
                        confidence = round(similarity, 3)

                        candidates.append({
                            "service_id": service_id,
                            "service_name": scenario_name,
                            "description": "",  # Не используем description в TagSearchService
                            "confidence": confidence,
                            "source": "tag_search",
                            "category": category,
                            "object": object_name,
                            "incident_type": incident_type,
                            "location_type": location_type
                        })

                    return candidates

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка в _search_with_trgm: {e}")
            return []

    def _preprocess_text(self, text: str) -> str:
        """Предобработка текста сообщения"""
        # Приводим к нижнему регистру
        text = text.lower()

        # Убираем лишние символы, оставляем буквы, цифры, пробелы
        text = re.sub(r'[^\w\s]', ' ', text)

        # Нормализуем пробелы
        text = re.sub(r'\s+', ' ', text).strip()

        return text
