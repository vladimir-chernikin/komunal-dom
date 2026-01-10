#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TagSearchService - микросервис поиска услуг по тегам
Использует таблицы services_catalog, service_tags и ref_tags
По ТЗ возвращает JSON {[КодУслуги]} без confidence
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
    """Микросервис поиска услуг по тегам (возвращает множества service_id)"""

    def __init__(self):
        self.service_cache = None
        self.morph = None
        logger.info("TagSearchService инициализирован")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    async def _load_services(self):
        """Асинхронная загрузка услуг из БД в кэш"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Загружаем услуги из services_catalog с их тегами и атрибутами
                    # ИСПРАВЛЕНО (2025-12-26): Добавлены incident_type, category, location_type
                    cursor.execute("""
                        SELECT sc.service_id, sc.scenario_name, sc.description_for_search,
                               sc.incident_type, sc.category, sc.location_type,
                               COALESCE(string_agg(rt.tag_name, ','), '') as tags
                        FROM services_catalog sc
                        LEFT JOIN service_tags st ON sc.service_id = st.service_id
                        LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id AND rt.is_active = TRUE
                        WHERE sc.is_active = TRUE
                        GROUP BY sc.service_id, sc.scenario_name, sc.description_for_search,
                                 sc.incident_type, sc.category, sc.location_type
                        ORDER BY sc.service_id
                    """)
                    services = cursor.fetchall()

                    service_cache = {}
                    for row in services:
                        service_id = row[0]
                        scenario_name = row[1]
                        description = row[2] or ""
                        incident_type = row[3] or ""
                        category = row[4] or ""
                        location_type = row[5] or ""
                        tags = row[6] or ""

                        # Извлекаем теги
                        # ИСПРАВЛЕНО (2026-01-10): Фильтруем слишком длинные "теги-предложения"
                        # Теги длиннее 30 символов - это целые предложения, которые вызывают ложные совпадения
                        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip() and len(tag.strip()) <= 30]

                        # ИСПРАВЛЕНО: Разбиваем теги-фразы на отдельные слова
                        # "течет труба" -> ["течет", "труба", "течет труба"]
                        expanded_tags = set(tag_list)
                        for tag in tag_list:
                            # Если тег содержит пробел - разбиваем на слова
                            if ' ' in tag:
                                words = tag.split()
                                expanded_tags.update(words)

                        # Дополняем словами из названия и описания
                        name_words = self._tokenize_text(scenario_name)
                        desc_words = self._tokenize_text(description)

                        # Все поисковые термины для этой услуги
                        all_search_terms = set(expanded_tags) | set(name_words) | set(desc_words)

                        service_cache[service_id] = {
                            'service_id': service_id,
                            'service_name': scenario_name,
                            'description': description,
                            'incident_type': incident_type,
                            'category': category,
                            'location_type': location_type,
                            'search_terms': all_search_terms
                        }
                    return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"TagSearchService: загружено {len(self.service_cache)} услуг из services_catalog")

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

        # ИСПРАВЛЕНО: Фильтруем короткие слова (минимум 3 буквы)
        # "течь", "вода", "кран" - важные слова из 4 букв!
        # Предлоги и союзы ("и", "в", "на", "у") - 1-2 буквы - отсеиваем
        return [w for w in words if len(w) > 2]

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод поиска услуги по тексту сообщения
        Возвращает JSON с множеством service_id (по ТЗ)

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для применения к кандидатам
                     {'incident_type': 'Инцидент', 'location_type': 'Индивидуальное', 'category': 'Водоснабжение'}

        ИСПРАВЛЕНО (2026-01-10): Добавлен параметр filters и логика фильтрации candidates
        """
        try:
            if not self.service_cache:
                await self._load_services()

            if not self.service_cache:
                return {"status": "error", "message": "Нет загруженных услуг", "candidates": []}

            # Предобработка текста
            clean_text = self._preprocess_text(message_text)
            words = clean_text.split()

            logger.info(f"TagSearchService: ищем по тексту '{clean_text}' (слова: {words})")

            # По ТЗ: возвращаем JSON {[КодУслуги], [Релевантность]}
            # Но для пересечений нам нужно только множество service_id
            matching_service_ids = set()

            for service_id, service_data in self.service_cache.items():
                # Проверяем есть ли совпадение
                if self._has_match(words, service_data['search_terms']):
                    matching_service_ids.add(service_id)

            # Формируем результат
            # ИСПРАВЛЕНО (2026-01-06): Вычисляем score на основе совпадений слов
            # ИСПРАВЛЕНО (2025-12-26): Добавлены incident_type, category, location_type
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
                    "matched_terms": matched_terms,
                    "source": "tag_search",
                    "incident_type": service_data.get('incident_type', ''),
                    "category": service_data.get('category', ''),
                    "location_type": service_data.get('location_type', '')
                })

            # ИСПРАВЛЕНО (2026-01-06): Нормализуем confidence
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

            # ИСПРАВЛЕНО (2026-01-10): Применяем фильтры к кандидатам
            # ИСПРАВЛЕНО (2026-01-10): Извлекаем .get('value') из словаря фильтров
            if filters:
                before_count = len(candidates)
                filtered = candidates

                # Helper функция для извлечения значения из фильтра
                def get_filter_value(filter_key):
                    """Извлекает value из фильтра, который может быть строкой или dict {'value': ..., 'confidence': ...}"""
                    filter_data = filters.get(filter_key)
                    if filter_data is None:
                        return None
                    if isinstance(filter_data, dict):
                        return filter_data.get('value')
                    return filter_data

                incident_value = get_filter_value('incident_type')
                if incident_value:
                    filtered = [c for c in filtered
                               if incident_value in c.get('incident_type', '')]
                    logger.info(f"TagSearch: Отфильтровано по incident_type={incident_value}: {len(filtered)} из {before_count}")

                location_value = get_filter_value('location_type')
                if location_value:
                    filtered = [c for c in filtered
                               if location_value in c.get('location_type', '')]
                    logger.info(f"TagSearch: Отфильтровано по location_type={location_value}: {len(filtered)} из {before_count}")

                category_value = get_filter_value('category')
                if category_value:
                    filtered = [c for c in filtered
                               if category_value.lower() in c.get('category', '').lower()]
                    logger.info(f"TagSearch: Отфильтровано по category={category_value}: {len(filtered)} из {before_count}")

                candidates = filtered

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

        ИСПРАВЛЕНО: Убрана агрессивная логика вхождения term in word
        ИСПРАВЛЕНО: Минимальная длина слов уменьшена до 3 букв (было 5)
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

            # ИСПРАВЛЕНО (2025-12-25): Пропускаем слишком короткие термины (минимум 4 букв)
            # "труба", "кран", "течь" - важные слова из 4-5 букв
            if len(term_lower) < 4:
                continue

            # ИСПРАВЛЕНО (2025-12-25): Проверяем что длина слова сообщения >= 4 букв
            valid_words = [w for w in message_words if len(w) >= 4]

            # Прямое совпадение
            if any(word == term_lower for word in valid_words):
                return True

            # Совпадение по нормальной форме
            if any(parsed == term_lower for parsed in message_normalized):
                return True

            # Вхождение слова в терм (ТОЛЬКО если word достаточно длинный)
            # УБРАНО: term_lower in word - создает ложные срабатывания
            for word in valid_words:
                # ИСПРАВЛЕНО (2025-12-25): Снижено до 5 букв
                if len(word) >= 5 and word in term_lower:
                    return True

            # Нечеткое совпадение (для опечаток) - только для длинных слов
            for word in valid_words:
                # ИСПРАВЛЕНО (2025-12-25): Снижено до 5 букв
                if len(word) >= 5 and len(term_lower) >= 5:
                    if fuzz.ratio(word, term_lower) > 85:
                        return True

        return False
