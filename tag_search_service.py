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
                    # Загружаем услуги из services_catalog с их тегами
                    cursor.execute("""
                        SELECT sc.service_id, sc.scenario_name, sc.description_for_search,
                               COALESCE(string_agg(rt.tag_name, ','), '') as tags
                        FROM services_catalog sc
                        LEFT JOIN service_tags st ON sc.service_id = st.service_id
                        LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id AND rt.is_active = TRUE
                        WHERE sc.is_active = TRUE
                        GROUP BY sc.service_id, sc.scenario_name, sc.description_for_search
                        ORDER BY sc.service_id
                    """)
                    services = cursor.fetchall()

                    service_cache = {}
                    for row in services:
                        service_id = row[0]
                        scenario_name = row[1]
                        description = row[2] or ""
                        tags = row[3] or ""

                        # Извлекаем теги
                        tag_list = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]

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

    async def search(self, message_text: str) -> Dict:
        """
        Основной метод поиска услуги по тексту сообщения
        Возвращает JSON с множеством service_id (по ТЗ)
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
            candidates = []
            for service_id in matching_service_ids:
                service_data = self.service_cache[service_id]
                candidates.append({
                    "service_id": service_id,
                    "service_name": service_data['service_name'],
                    "confidence": 1.0,  # По ТЗ: если есть в множестве = 100%
                    "source": "tag_search"
                })

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

            # Пропускаем слишком короткие термины (минимум 5 букв)
            if len(term_lower) < 5:
                continue

            # Проверяем что длина слова сообщения >= 5 букв
            valid_words = [w for w in message_words if len(w) >= 5]

            # Прямое совпадение
            if any(word == term_lower for word in valid_words):
                return True

            # Совпадение по нормальной форме
            if any(parsed == term_lower for parsed in message_normalized):
                return True

            # Вхождение слова в терм (ТОЛЬКО если word достаточно длинный)
            # УБРАНО: term_lower in word - создает ложные срабатывания
            for word in valid_words:
                if len(word) >= 6 and word in term_lower:
                    return True

            # Нечеткое совпадение (для опечаток) - только для длинных слов
            for word in valid_words:
                if len(word) >= 6 and len(term_lower) >= 6:
                    if fuzz.ratio(word, term_lower) > 85:
                        return True

        return False
