#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TrigramSearchService - микросервис поиска на основе триграммного индекса PostgreSQL pg_trgm
Использует нечеткий поиск с порогом схожести и морфологическую нормализацию
"""

import logging
import re
import pymorphy2
from typing import List, Dict, Any
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class TrigramSearchService:
    """Микросервис поиска услуг на основе триграммного индекса"""

    def __init__(self):
        self.service_cache = None
        self.morph = None  # Ленивая инициализация
        self.similarity_threshold = 0.3  # Порог схожести для pg_trgm
        logger.info("TrigramSearchService инициализирован")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    def _normalize_text(self, text: str) -> str:
        """
        Нормализация текста с морфологией для триграммного поиска

        Returns:
            str: Нормализованный текст для поиска
        """
        try:
            morph = self._get_morph()
            words = re.findall(r'\b\w+\b', text.lower())
            normalized_words = []

            for word in words:
                if len(word) < 2:
                    continue
                parsed = morph.parse(word)[0]
                normalized_words.append(parsed.normal_form)

            return ' '.join(normalized_words)

        except Exception as e:
            logger.error(f"Ошибка в нормализации текста: {e}")
            return text.lower()

    async def _load_services(self):
        """Загрузка услуг из БД с триграммными индексами"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Проверяем наличие триграммного индекса
                    cursor.execute("""
                        SELECT indexname
                        FROM pg_indexes
                        WHERE tablename = 'services'
                        AND indexdef LIKE '%gin%'
                        AND indexdef LIKE '%gin_trgm_ops%'
                    """)
                    trigram_indexes = cursor.fetchall()

                    if not trigram_indexes:
                        logger.info("TrigramSearchService: создаем триграммный индекс...")
                        cursor.execute("""
                            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_services_search_trgm
                            ON services USING gin ((name || ' ' || COALESCE(tags, '') || ' ' || COALESCE(keywords, '')) gin_trgm_ops)
                        """)
                        logger.info("TrigramSearchService: триграммный индекс создан")
                    else:
                        logger.info(f"TrigramSearchService: найдены индексы: {[idx[0] for idx in trigram_indexes]}")

                    # Загружаем услуги
                    cursor.execute("""
                        SELECT id, name, category, object_type,
                               incident_type, location_type, tags, keywords
                        FROM services_catalog sc
                        WHERE is_active = TRUE
                    """)
                    services = cursor.fetchall()

                service_cache = {}
                morph = self._get_morph()

                for service_id, name, category, object_type, incident_type, location_type, tags, keywords in services:
                    # Создаем расширенный поисковый текст
                    search_text_parts = [name]
                    if tags:
                        search_text_parts.append(tags)
                    if keywords:
                        search_text_parts.append(keywords)

                    # Нормализуем текст для поиска
                    search_text = ' '.join(search_text_parts)
                    normalized_search_text = self._normalize_text(search_text)

                    service_cache[service_id] = {
                        'name': name,
                        'category': category or '',
                        'object_type': object_type or '',
                        'incident_type': incident_type or '',
                        'location_type': location_type or '',
                        'search_text': search_text.lower(),
                        'normalized_search_text': normalized_search_text,
                        'tags': tags or '',
                        'keywords': keywords or ''
                    }

                return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"TrigramSearchService: загружено {len(self.service_cache)} услуг")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = {}

    async def search(self, message_text: str) -> Dict:
        """
        Поиск услуг с помощью триграммного индекса

        Args:
            message_text: Текст сообщения пользователя

        Returns:
            Dict: Результат поиска в формате JSON
        """
        try:
            logger.info(f"TrigramSearch: поиск по тексту '{message_text[:50]}...'")

            if self.service_cache is None:
                await self._load_services()

            if not self.service_cache:
                return {'candidates': [], 'error': 'Услуги не загружены'}

            # Нормализуем текст запроса
            normalized_query = self._normalize_text(message_text)
            original_query = message_text.lower()

            logger.info(f"TrigramSearch: исходный '{message_text}' -> нормализованный '{normalized_query}'")

            # Ищем в PostgreSQL с помощью триграммного индекса
            candidates = await self._trigram_search_db(normalized_query, original_query)

            # Дополнительный пост-фильтр с морфологией для улучшения результатов
            enhanced_candidates = await self._enhance_results_with_morphology(
                candidates, normalized_query, message_text
            )

            result = {
                'status': 'success',
                'candidates': enhanced_candidates[:5],  # Возвращаем топ-5
                'total_matches': len(enhanced_candidates),
                'method': 'trigram_search'
            }

            logger.info(f"TrigramSearch: найдено услуг: {len(enhanced_candidates)}")
            return result

        except Exception as e:
            logger.error(f"Ошибка в TrigramSearchService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }

    async def _trigram_search_db(self, normalized_query: str, original_query: str) -> List[Dict]:
        """
        Поиск в БД с помощью триграммного индекса
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # Ищем по нормализованному запросу
                    cursor.execute("""
                        SELECT id, name,
                               similarity(name || ' ' || COALESCE(tags, '') || ' ' || COALESCE(keywords, ''), %s) as name_similarity,
                               similarity(%s, name || ' ' || COALESCE(tags, '') || ' ' || COALESCE(keywords, '')) as query_similarity
                        FROM services_catalog sc
                        WHERE is_active = TRUE
                        AND (similarity(name || ' ' || COALESCE(tags, '') || ' ' || COALESCE(keywords, ''), %s) > %s
                             OR similarity(%s, name || ' ' || COALESCE(tags, '') || ' ' || COALESCE(keywords, '')) > %s)
                        ORDER BY GREATEST(name_similarity, query_similarity) DESC
                        LIMIT 10
                    """, [normalized_query, original_query, normalized_query, self.similarity_threshold,
                          original_query, self.similarity_threshold])

                    results = cursor.fetchall()
                    return results

            db_results = await sync_to_async(search_sync)()

            candidates = []
            for service_id, name, name_similarity, query_similarity in db_results:
                # Берем максимальную схожесть
                similarity = max(name_similarity, query_similarity)

                candidates.append({
                    'service_id': service_id,
                    'service_name': name,
                    'confidence': round(similarity, 3),
                    'source': 'trigram_search',
                    'db_similarity': similarity
                })

            return candidates

        except Exception as e:
            logger.error(f"Ошибка триграммного поиска в БД: {e}")
            return []

    async def _enhance_results_with_morphology(self, candidates: List[Dict],
                                            normalized_query: str, original_query: str) -> List[Dict]:
        """
        Улучшение результатов с помощью морфологического анализа
        """
        try:
            enhanced_candidates = []
            morph = self._get_morph()

            query_words = set(normalized_query.split() + original_query.lower().split())

            for candidate in candidates:
                service_id = candidate['service_id']
                if service_id not in self.service_cache:
                    continue

                service_info = self.service_cache[service_id]

                # Получаем слова из текста услуги
                service_text = service_info['normalized_search_text']
                service_words = set(service_text.split())

                # Считаем морфологические совпадения
                morph_matches = len(query_words.intersection(service_words))
                morph_ratio = morph_matches / max(len(query_words), 1)

                # Увеличиваем уверенность с учетом морфологии
                base_confidence = candidate['confidence']
                morphology_bonus = morph_ratio * 0.3  # До 30% бонуса за морфологию
                enhanced_confidence = min(base_confidence + morphology_bonus, 1.0)

                enhanced_candidate = candidate.copy()
                enhanced_candidate['confidence'] = round(enhanced_confidence, 3)
                enhanced_candidate['morphology_matches'] = morph_matches
                enhanced_candidate['morphology_ratio'] = round(morph_ratio, 3)

                # Учитываем только если выше порога
                if enhanced_confidence >= 0.4:
                    enhanced_candidates.append(enhanced_candidate)

            # Сортируем по улучшенной уверенности
            enhanced_candidates.sort(key=lambda x: x['confidence'], reverse=True)
            return enhanced_candidates

        except Exception as e:
            logger.error(f"Ошибка улучшения результатов морфологией: {e}")
            return candidates