#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SemanticSearchService - микросервис поиска услуг по контенту
Использует pymorphy2 для морфологии и rapidfuzz для нечеткого совпадения
Ищет по scenario_name и description_for_search (БЕЗ ТЕГОВ)
"""

import logging
import re
from typing import List, Dict, Set
from django.db import connection
from asgiref.sync import sync_to_async
import pymorphy2
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class SemanticSearchService:
    """Микросервис поиска услуг по контенту (название + описание)"""

    def __init__(self):
        self.service_cache = None
        self.morph = None
        logger.info("SemanticSearchService инициализирован (поиск по КОНТЕНТУ)")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    async def _load_services(self, filters: Dict = None):
        """
        Асинхронная загрузка услуг из БД в кэш

        ИСПРАВЛЕНО (2026-01-13):
        - Загружает scenario_name и description_for_search (БЕЗ ТЕГОВ)
        - Добавлена предварительная фильтрация по filters (только confidence >= 90%)
        """
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Строим SQL запрос с фильтрами
                    sql = """
                        SELECT sc.service_id, sc.scenario_name, sc.description_for_search,
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
                        description = row[2] or ""
                        category = row[3] or ""
                        object_name = row[4] or ""
                        incident_type = row[5] or ""
                        location_type = row[6] or ""

                        # Формируем поисковые термины из названия и описания (БЕЗ ТЕГОВ!)
                        name_words = self._tokenize_text(scenario_name)
                        desc_words = self._tokenize_text(description)

                        # Все поисковые термины для этой услуги
                        all_search_terms = set(name_words) | set(desc_words)

                        service_cache[service_id] = {
                            'service_id': service_id,
                            'service_name': scenario_name,
                            'description': description,
                            'category': category,
                            'object_name': object_name,
                            'incident_type': incident_type,
                            'location_type': location_type,
                            'search_terms': all_search_terms
                        }
                    return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"SemanticSearchService: загружено {len(self.service_cache)} услуг")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = {}

    def _tokenize_text(self, text: str) -> List[str]:
        """Разбивает текст на слова, убирая лишние символы"""
        if not text:
            return []

        # Приводим к нижнему регистру
        text = text.lower()

        # Убираем лишние символы
        text = re.sub(r'[^\w\s]', ' ', text)

        # Разбиваем на слова
        words = text.split()

        # Фильтруем короткие слова (минимум 3 буквы)
        return [w for w in words if len(w) > 2]

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод поиска услуги по тексту сообщения
        Ищет по scenario_name и description (БЕЗ ТЕГОВ)

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для предварительной фильтрации в SQL

        Returns:
            Dict: Результат поиска в формате JSON {status, candidates: [{...}]}

        ИСПРАВЛЕНО (2026-01-13):
        - Ищет по scenario_name и description_for_search (БЕЗ ТЕГОВ)
        - Использует pymorphy2 для морфологии
        - Использует rapidfuzz для нечеткого совпадения
        """
        try:
            # Предварительная фильтрация через загрузку услуг
            if not self.service_cache:
                await self._load_services(filters)

            if not self.service_cache:
                return {"status": "error", "message": "Нет загруженных услуг", "candidates": []}

            # Предобработка текста
            clean_text = self._preprocess_text(message_text)
            words = clean_text.split()

            logger.info(f"SemanticSearchService: поиск по тексту '{clean_text}' (поиск по КОНТЕНТУ)")

            # Поиск по search_terms (название + описание)
            matching_service_ids = set()

            for service_id, service_data in self.service_cache.items():
                # Проверяем есть ли совпадение
                if self._has_match(words, service_data['search_terms']):
                    matching_service_ids.add(service_id)

            # Формируем результат
            candidates_with_scores = []
            for service_id in matching_service_ids:
                service_data = self.service_cache[service_id]

                # Вычисляем score: количество совпавших слов
                matched_terms = 0
                for word in words:
                    if len(word) < 4:
                        continue
                    for term in service_data['search_terms']:
                        if len(term) < 4:
                            continue
                        if word == term or word in term or term in word:
                            matched_terms += 1
                            break

                candidates_with_scores.append({
                    "service_id": service_id,
                    "service_name": service_data['service_name'],
                    "description": service_data['description'],
                    "matched_terms": matched_terms,
                    "source": "semantic_search",
                    "category": service_data.get('category', ''),
                    "object": service_data.get('object_name', ''),
                    "incident_type": service_data.get('incident_type', ''),
                    "location_type": service_data.get('location_type', '')
                })

            # Нормализуем confidence
            if candidates_with_scores:
                # Вычисляем общую сумму scores
                total_score = sum(c["matched_terms"] for c in candidates_with_scores)

                if total_score == 0:
                    # Если нет совпадений - всем равная вероятность
                    n = len(candidates_with_scores)
                    confidence_per_candidate = 1.0 / n
                    for c in candidates_with_scores:
                        c["confidence"] = confidence_per_candidate
                else:
                    # Вычисляем confidence пропорционально score
                    for c in candidates_with_scores:
                        c["confidence"] = c["matched_terms"] / total_score

            # Убираем matched_terms из финального результата
            candidates = [
                {k: v for k, v in c.items() if k != "matched_terms"}
                for c in candidates_with_scores
            ]

            if candidates:
                return {
                    "status": "success",
                    "candidates": candidates,
                    "method": "semantic_search"
                }
            else:
                return {
                    "status": "not_found",
                    "candidates": [],
                    "method": "semantic_search"
                }

        except Exception as e:
            logger.error(f"Ошибка в SemanticSearchService.search: {e}")
            return {
                "status": "error",
                "message": f"Ошибка поиска: {str(e)}",
                "candidates": []
            }

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
        Проверяет есть ли совпадение между словами сообщения и терминами услуги
        Использует pymorphy2 для морфологии и rapidfuzz для нечеткого совпадения
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

        # Проверяем совпадение с терминами услуги
        for term in search_terms:
            term_lower = term.lower()

            # Пропускаем слишком короткие термины (минимум 4 букв)
            if len(term_lower) < 4:
                continue

            # Проверяем что длина слова сообщения >= 4 букв
            valid_words = [w for w in message_words if len(w) >= 4]

            # Прямое совпадение
            if any(word == term_lower for word in valid_words):
                return True

            # Совпадение по нормальной форме
            if any(parsed == term_lower for parsed in message_normalized):
                return True

            # Вхождение слова в терм (ТОЛЬКО если word достаточно длинный)
            for word in valid_words:
                if len(word) >= 5 and word in term_lower:
                    return True

            # Нечеткое совпадение (для опечаток) - только для длинных слов
            for word in valid_words:
                if len(word) >= 5 and len(term_lower) >= 5:
                    if fuzz.ratio(word, term_lower) > 85:
                        return True

        return False
