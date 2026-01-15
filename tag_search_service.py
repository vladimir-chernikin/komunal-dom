#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TagSearchService - микросервис поиска услуг по тегам
Использует триграммные индексы (pg_trgm) + pymorphy2 + rapidfuzz
Ищет ТОЛЬКО ПО ТЕГАМ из ref_tags
"""

import logging
import re
from typing import List, Dict, Set
from django.db import connection
from asgiref.sync import sync_to_async
import pymorphy2
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class TagSearchService:
    """Микросервис поиска услуг по тегам (pg_trgm + pymorphy2 + rapidfuzz)"""

    def __init__(self):
        # ИСПРАВЛЕНО (2026-01-13): УБРАНО кэширование для избежания проблем с памятью и параллельными запросами
        self.morph = None
        logger.info("TagSearchService инициализирован (поиск по ТЕГАМ с pg_trgm + pymorphy2 + rapidfuzz БЕЗ кэша)")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

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

                    # ИСПРАВЛЕНО (2026-01-13): Только фильтры, которые существуют в MainAgent
                    if filters:
                        category_data = filters.get('category')
                        if category_data and isinstance(category_data, dict):
                            category_conf = category_data.get('confidence', 0)
                            if category_conf >= 0.9:
                                sql += " AND rc.category_name = %s"
                                params.append(category_data.get('value'))

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

            service_cache = await sync_to_async(load_sync)()
            logger.info(f"TagSearchService: загружено {len(service_cache)} услуг")
            return service_cache  # ИСПРАВЛЕНО (2026-01-13): Возвращаем напрямую, без кэширования

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            return {}  # ИСПРАВЛЕНО (2026-01-13): Возвращаем пустой словарь

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод поиска услуги по тексту сообщения
        Ищет ТОЛЬКО ПО ТЕГАМ с комбинированным подходом: pg_trgm + pymorphy2 + rapidfuzz

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для предварительной фильтрации в SQL

        Returns:
            Dict: Результат поиска в формате JSON {status, candidates: [{...}]}

        ИСПРАВЛЕНО (2026-01-13):
        - Шаг 1: pg_trgm (word_similarity) для быстрого первичного отбора кандидатов
        - Шаг 2: pymorphy2 для морфологического анализа слов
        - Шаг 3: rapidfuzz для нечеткого совпадения (опечатки)
        - Ищет только по тегам (scenario_name и description НЕ участвуют)
        """
        try:
            # ИСПРАВЛЕНО (2026-01-13): ВСЕГДА загружаем услуги налету (БЕЗ кэша)
            service_cache = await self._load_services(filters)

            if not service_cache:
                return {"status": "error", "message": "Нет загруженных услуг", "candidates": []}

            # Предобработка текста
            clean_text = self._preprocess_text(message_text)
            words = clean_text.split()

            logger.info(f"TagSearchService: поиск по тексту '{clean_text}' (слова: {words})")

            # ШАГ 1: Быстрый первичный отбор через pg_trgm
            candidate_ids = await self._search_with_trgm(clean_text)

            if not candidate_ids:
                return {
                    "status": "not_found",
                    "candidates": [],
                    "method": "tag_search"
                }

            logger.info(f"TagSearchService: pg_trgm отобрал {len(candidate_ids)} кандидатов")

            # ШАГ 2 + 3: Точное совпадение с pymorphy2 + rapidfuzz
            matching_service_ids = set()

            # Получаем теги для кандидатов
            tags_for_candidates = await self._get_tags_for_candidates(candidate_ids)

            for service_id in candidate_ids:
                tags = tags_for_candidates.get(service_id, set())

                # Проверяем совпадение с pymorphy2 + rapidfuzz
                if self._has_match(words, tags):
                    matching_service_ids.add(service_id)

            logger.info(f"TagSearchService: после точного совпадения: {len(matching_service_ids)} кандидатов")

            # Формируем результат
            candidates = await self._format_candidates(matching_service_ids, service_cache)

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

    async def _search_with_trgm(self, message_text: str) -> Set[int]:
        """
        ШАГ 1: Быстрый первичный отбор кандидатов с помощью триграммного индекса (pg_trgm)
        Возвращает только ID услуг для дальнейшего анализа

        ИСПРАВЛЕНО (2026-01-15): Разбивает текст на слова и ищет по КАЖДОМУ слову отдельно
        ИСПРАВЛЕНО (2026-01-13): Возвращает Set[int] вместо List[Dict]
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-01-15): Разбиваем текст на слова (минимум 3 буквы)
                    # word_similarity работает плохо с целыми предложениями
                    words = [w.strip(',.!?;:"\'-') for w in message_text.split()
                            if len(w.strip(',.!?;:"\'-')) >= 3]

                    if not words:
                        return set()

                    # Ищем по каждому слову отдельно (UNION)
                    all_service_ids = set()

                    for word in words:
                        cursor.execute("""
                            SELECT DISTINCT sc.service_id
                            FROM services_catalog sc
                            LEFT JOIN service_tags st ON sc.service_id = st.service_id
                            LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id AND rt.is_active = TRUE
                            WHERE sc.is_active = TRUE
                              AND word_similarity(%s, rt.tag_name) > 0.3
                        """, [word.lower()])

                        results = cursor.fetchall()
                        all_service_ids.update({row[0] for row in results})

                    return all_service_ids

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка в _search_with_trgm: {e}")
            return set()

    async def _get_tags_for_candidates(self, service_ids: Set[int]) -> Dict[int, Set[str]]:
        """
        Загружает теги для указанных кандидатов

        Args:
            service_ids: Set ID услуг

        Returns:
            Dict {service_id: set of tags}
        """
        try:
            if not service_ids:
                return {}

            def load_sync():
                with connection.cursor() as cursor:
                    # Получаем теги для кандидатов
                    placeholders = ','.join(['%s'] * len(service_ids))
                    cursor.execute(f"""
                        SELECT sc.service_id, COALESCE(string_agg(rt.tag_name, ','), '') as tags
                        FROM services_catalog sc
                        LEFT JOIN service_tags st ON sc.service_id = st.service_id
                        LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id AND rt.is_active = TRUE
                        WHERE sc.service_id IN ({placeholders})
                        GROUP BY sc.service_id
                    """, list(service_ids))

                    results = cursor.fetchall()

                    tags_dict = {}
                    for row in results:
                        service_id = row[0]
                        tags = row[1] or ""

                        # Разбиваем теги и фильтруем длинные
                        tag_list = [tag.strip().lower() for tag in tags.split(',')
                                     if tag.strip() and len(tag.strip()) <= 30]

                        # Расширяем теги-фразы
                        expanded_tags = set(tag_list)
                        for tag in tag_list:
                            if ' ' in tag:
                                words = tag.split()
                                expanded_tags.update(words)

                        tags_dict[service_id] = expanded_tags

                    return tags_dict

            return await sync_to_async(load_sync)()

        except Exception as e:
            logger.error(f"Ошибка в _get_tags_for_candidates: {e}")
            return {}

    async def _format_candidates(self, service_ids: Set[int], service_cache: Dict) -> List[Dict]:
        """
        Формирует кандидатов из ID услуг с вычислением confidence

        Args:
            service_ids: Set ID услуг
            service_cache: Словарь услуг (ИСПРАВЛЕНО 2026-01-13: передаем как параметр)

        Returns:
            List of candidate dicts
        """
        try:
            if not service_ids:
                return []

            candidates = []
            n = len(service_ids)

            # Равномерное распределение confidence
            base_confidence = 1.0 / n if n > 0 else 0.0

            for service_id in service_ids:
                service_data = service_cache.get(service_id)  # ИСПРАВЛЕНО (2026-01-13): используем параметр
                if service_data:
                    candidates.append({
                        "service_id": service_id,
                        "service_name": service_data['service_name'],
                        "description": "",  # Не используем description в TagSearchService
                        "confidence": round(base_confidence, 3),
                        "source": "tag_search",
                        "category": service_data.get('category', ''),
                        "object": service_data.get('object_name', ''),
                        "incident_type": service_data.get('incident_type', ''),
                        "location_type": service_data.get('location_type', '')
                    })

            return candidates

        except Exception as e:
            logger.error(f"Ошибка в _format_candidates: {e}")
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

    def _has_match(self, message_words: List[str], search_terms: Set[str]) -> bool:
        """
        ШАГ 2+3: Проверяет точное совпадение между словами сообщения и терминами (тегами)
        Использует pymorphy2 для морфологии и rapidfuzz для нечеткого совпадения

        Args:
            message_words: Список слов из сообщения
            search_terms: Множество терминов (тегов) для сравнения

        Returns:
            True если есть совпадение, иначе False
        """
        morph = self._get_morph()

        # Нормализуем слова сообщения (только слова >= 3 букв)
        message_normalized = set()
        for word in message_words:
            if len(word) < 3:
                continue
            parsed = morph.parse(word)[0]
            message_normalized.add(parsed.normal_form)
            message_normalized.add(word)

        # Проверяем совпадение с терминами (тегами)
        for term in search_terms:
            term_lower = term.lower()

            # Пропускаем слишком короткие термины (минимум 4 букв)
            if len(term_lower) < 4:
                continue

            # Проверяем что длина слова сообщения >= 4 букв
            valid_words = [w for w in message_words if len(w) >= 4]

            # 1. Прямое совпадение
            if any(word == term_lower for word in valid_words):
                return True

            # 2. Совпадение по нормальной форме (морфология pymorphy2)
            if any(parsed == term_lower for parsed in message_normalized):
                return True

            # 3. Вхождение слова в терм (ТОЛЬКО если word достаточно длинный)
            for word in valid_words:
                if len(word) >= 5 and word in term_lower:
                    return True

            # 4. Нечеткое совпадение (для опечаток rapidfuzz) - только для длинных слов
            for word in valid_words:
                if len(word) >= 5 and len(term_lower) >= 5:
                    if fuzz.ratio(word, term_lower) > 85:
                        return True

        return False
