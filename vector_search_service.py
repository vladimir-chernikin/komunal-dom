#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VectorSearchService - микросервис поиска услуг с триграммным индексом
Использует pg_trgm для нечеткого поиска по scenario_name и description_for_search
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
        self.service_cache = None
        logger.info("VectorSearchService инициализирован")

    async def _load_services(self):
        """Асинхронная загрузка услуг из БД"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT service_id, scenario_name, description_for_search
                        FROM services_catalog
                        WHERE is_active = TRUE
                    """)
                    services = cursor.fetchall()

                service_cache = {}
                for service_id, scenario_name, description in services:
                    search_text = f"{scenario_name} {description or ''}".lower()
                    service_cache[service_id] = {
                        'service_id': service_id,
                        'service_name': scenario_name,
                        'description': description or '',
                        'search_text': search_text
                    }

                return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"VectorSearchService: загружено {len(self.service_cache)} услуг")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = {}

    async def search(self, message_text: str) -> Dict:
        """
        Поиск услуг с триграммным поиском через pg_trgm

        Args:
            message_text: Текст сообщения пользователя

        Returns:
            Dict: Результат поиска в формате JSON {[КодУслуги], [Релевантность]}
        """
        try:
            logger.info(f"VectorSearch: поиск по тексту '{message_text[:50]}...'")

            # Загружаем услуги если еще не загружены
            if self.service_cache is None:
                await self._load_services()

            if not self.service_cache:
                return {'status': 'error', 'candidates': [], 'error': 'Услуги не загружены'}

            # Нормализуем текст сообщения
            message_clean = re.sub(r'[^\w\s]', ' ', message_text.lower())
            message_clean = re.sub(r'\s+', ' ', message_clean).strip()

            # Используем pg_trgm для прямого поиска в БД
            candidates = await self._search_with_pg_trgm(message_clean)

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

    async def _search_with_pg_trgm(self, message_text: str) -> List[Dict]:
        """
        Поиск с использованием pg_trgm через SQL

        ИСПРАВЛЕНО: Для коротких запросов (< 5 букв) используем ILIKE вместо word_similarity
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # Для коротких запросов используем ILIKE (точное вхождение)
                    if len(message_text) < 5:
                        cursor.execute("""
                            SELECT
                                sc.service_id,
                                sc.scenario_name as service_name,
                                0.5 as similarity
                            FROM services_catalog sc
                            WHERE sc.is_active = TRUE
                              AND (
                                  sc.scenario_name ILIKE %s
                                  OR sc.description_for_search ILIKE %s
                              )
                            LIMIT 10
                        """, [f'%{message_text}%', f'%{message_text}%'])
                    else:
                        # Для длинных запросов используем word_similarity
                        cursor.execute("""
                            SELECT
                                sc.service_id,
                                sc.scenario_name as service_name,
                                COALESCE(
                                    GREATEST(
                                        word_similarity(%s, sc.scenario_name),
                                        word_similarity(%s, sc.description_for_search)
                                    ),
                                    0
                                ) as similarity
                            FROM services_catalog sc
                            WHERE sc.is_active = TRUE
                              AND (
                                  word_similarity(%s, sc.scenario_name) > 0.2
                                  OR word_similarity(%s, sc.description_for_search) > 0.2
                              )
                            ORDER BY similarity DESC
                            LIMIT 10
                        """, [message_text, message_text, message_text, message_text])

                    results = cursor.fetchall()

                candidates = []
                for service_id, service_name, similarity in results:
                    if similarity > 0.2:
                        candidates.append({
                            'service_id': service_id,
                            'service_name': service_name,
                            'confidence': round(similarity, 3),
                            'source': 'vector_search'
                        })

                return candidates

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка триграммного поиска: {e}")
            # Фоллбек на простой поиск
            return await self._fallback_search(message_text)

    async def _fallback_search(self, message_text: str) -> List[Dict]:
        """Фоллбек на простой поиск через LIKE"""
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT service_id, scenario_name as service_name
                        FROM services_catalog
                        WHERE is_active = TRUE
                          AND (
                              scenario_name ILIKE %s
                              OR description_for_search ILIKE %s
                          )
                        LIMIT 10
                    """, [f'%{message_text}%', f'%{message_text}%'])

                    results = cursor.fetchall()

                candidates = []
                for service_id, service_name in results:
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service_name,
                        'confidence': 0.5,  # Фиксированная уверенность для LIKE поиска
                        'source': 'vector_search_fallback'
                    })

                return candidates

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка фоллбек поиска: {e}")
            return []
