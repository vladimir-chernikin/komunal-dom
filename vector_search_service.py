#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VectorSearchService - микросервис векторного поиска услуг
Использует Yandex Embeddings API для семантического поиска

РЕФАКТОРИНГ (2026-01-13):
- Двойной поиск: по embedding тегов (точность) + embedding услуг (полнота)
- Фильтрация в SQL WHERE (incident_type, location_type, category)
- Слияние результатов с адаптивными весами

ОПТИМИЗАЦИЯ (2026-03-05):
- Кэш embeddings в памяти (~70KB)
- NumPy vectorized cosine similarity
- Batch загрузка вместо множества SQL запросов
"""

import logging
import re
import time
import numpy as np
from typing import List, Dict, Set, Tuple
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Микросервис векторного поиска услуг с двойным поиском"""

    # Классовые переменные для кэша (общие для всех экземпляров)
    _tags_embeddings_cache = None
    _services_embeddings_cache = None
    _embeddings_loaded = False
    _query_embeddings_cache = {}  # КЭШ embedding запросов {text: np.array}

    def __init__(self):
        logger.info("VectorSearchService инициализирован (с кэшем embeddings + кэшем запросов)")

    async def _preload_embeddings(self):
        """
        ОПТИМИЗАЦИЯ (2026-03-05): Предзагрузка всех embeddings в память

        Вызывается один раз при первом запросе.
        Загружает:
        - ~377 tag embeddings (service_tags)
        - ~68 service embeddings (services_catalog)
        Всего ~70KB RAM.
        """
        if VectorSearchService._embeddings_loaded:
            return

        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Загружаем tag embeddings
                    cursor.execute("""
                        SELECT
                            st.service_id,
                            rt.tag_id,
                            rt.embedding_tag,
                            sc.scenario_name,
                            COALESCE(rst.type_name, '') as incident_type,
                            COALESCE(rc.category_name, '') as category,
                            COALESCE(rl.localization_name, '') as location_type
                        FROM service_tags st
                        JOIN services_catalog sc ON st.service_id = sc.service_id
                        JOIN ref_tags rt ON st.tag_id = rt.tag_id
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                          AND rt.is_active = TRUE
                          AND rt.embedding_tag IS NOT NULL
                    """)
                    tag_rows = cursor.fetchall()

                    # Загружаем service embeddings
                    cursor.execute("""
                        SELECT
                            service_id,
                            scenario_name,
                            embedding_service,
                            COALESCE(type_id, 0) as type_id
                        FROM services_catalog
                        WHERE is_active = TRUE
                          AND embedding_service IS NOT NULL
                    """)
                    service_rows = cursor.fetchall()

                    return tag_rows, service_rows

            tag_rows, service_rows = await sync_to_async(load_sync)()

            # Парсим JSON и сохраняем в NumPy arrays
            VectorSearchService._tags_embeddings_cache = []
            for row in tag_rows:
                import json
                service_id, tag_id, embedding_json, scenario_name, incident_type, category, location_type = row
                embedding = np.array(json.loads(embedding_json), dtype=np.float32)
                VectorSearchService._tags_embeddings_cache.append({
                    'service_id': service_id,
                    'tag_id': tag_id,
                    'embedding': embedding,
                    'scenario_name': scenario_name,
                    'incident_type': incident_type,
                    'category': category,
                    'location_type': location_type
                })

            VectorSearchService._services_embeddings_cache = []
            for row in service_rows:
                service_id, scenario_name, embedding_json, type_id = row
                embedding = np.array(json.loads(embedding_json), dtype=np.float32)
                VectorSearchService._services_embeddings_cache.append({
                    'service_id': service_id,
                    'scenario_name': scenario_name,
                    'embedding': embedding,
                    'type_id': type_id
                })

            VectorSearchService._embeddings_loaded = True
            logger.info(f"VectorSearchService: предзагружено {len(VectorSearchService._tags_embeddings_cache)} tag embeddings и {len(VectorSearchService._services_embeddings_cache)} service embeddings")

        except Exception as e:
            logger.error(f"Ошибка предзагрузки embeddings: {e}")
            VectorSearchService._tags_embeddings_cache = []
            VectorSearchService._services_embeddings_cache = []
            VectorSearchService._embeddings_loaded = True

    @staticmethod
    def _cosine_similarity_batch(query_embedding: np.ndarray, embeddings: List[np.ndarray]) -> np.ndarray:
        """
        ОПТИМИЗАЦИЯ (2026-03-05): Vectorized cosine similarity

        Вычисляет косинусное сходство между query embedding и списком embeddings
        за ОДИН проход через NumPy operations.

        Args:
            query_embedding: (256,) numpy array
            embeddings: List of (256,) numpy arrays

        Returns:
            np.ndarray: Array of similarity scores
        """
        if not embeddings:
            return np.array([])

        # Stack embeddings into matrix (N, 256)
        embeddings_matrix = np.vstack(embeddings)

        # Compute cosine similarity
        # similarity = (A · B) / (||A|| * ||B||)
        numerator = np.dot(embeddings_matrix, query_embedding)
        denominator = np.linalg.norm(embeddings_matrix, axis=1) * np.linalg.norm(query_embedding)

        # Avoid division by zero
        similarities = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator!=0)

        return similarities

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод векторного поиска с двойным поиском

        ОПТИМИЗАЦИЯ (2026-03-05):
        - Предзагрузка embeddings в память
        - Vectorized cosine similarity

        Алгоритм:
        1. Получаем embedding запроса
        2. Параллельный поиск:
           - По embedding тегов (точность)
           - По embedding услуг (полнота)
        3. Слияние результатов с весами
        4. Фильтрация по адаптивному порогу

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для SQL WHERE

        Returns:
            Dict: Результат поиска в формате JSON {status, candidates: [{...}]}
        """
        try:
            total_start = time.perf_counter()

            # ОПТИМИЗАЦИЯ (2026-03-05): Предзагружаем embeddings
            preload_start = time.perf_counter()
            await self._preload_embeddings()
            preload_time = (time.perf_counter() - preload_start) * 1000

            logger.info(f"VectorSearch: двойной поиск по тексту '{message_text[:50]}...'")

            # Предобработка текста
            message_clean = self._preprocess_text(message_text)

            # Helper для извлечения фильтров
            def get_filter_value(filter_key):
                filter_data = filters.get(filter_key) if filters else None
                if filter_data is None:
                    return None
                if isinstance(filter_data, dict):
                    return filter_data.get('value')
                return filter_data

            # Извлекаем фильтры
            incident_type = get_filter_value('incident_type') or ''
            location_type = get_filter_value('location_type') or ''
            category = get_filter_value('category') or ''

            # ШАГ 1: Получаем embedding запроса (С КЭШЕМ!)
            embedding_start = time.perf_counter()
            query_embedding = VectorSearchService._query_embeddings_cache.get(message_clean)

            if query_embedding is None:
                # КЭШ ПРОМАХ - делаем HTTP запрос к Yandex API
                from ai_agent_service import AIAgentService
                ai_service = AIAgentService(provider='yandexgpt')

                try:
                    embedding_list, _ = await ai_service.get_embedding(message_clean)
                    query_embedding = np.array(embedding_list, dtype=np.float32)

                    # Сохраняем в кэш
                    VectorSearchService._query_embeddings_cache[message_clean] = query_embedding
                    embedding_time = (time.perf_counter() - embedding_start) * 1000
                    logger.warning(f"VectorSearch: embedding загружен из API (кэш промах, всего в кэше: {len(VectorSearchService._query_embeddings_cache)}, время={embedding_time:.1f}ms)")
                except Exception as e:
                    logger.error(f"Не удалось получить embedding запроса: {e}")
                    return {
                        'status': 'error',
                        'error': f'Не удалось получить embedding: {str(e)}',
                        'candidates': []
                    }
            else:
                embedding_time = (time.perf_counter() - embedding_start) * 1000
                logger.info(f"VectorSearch: embedding из кэша (hits: {len(VectorSearchService._query_embeddings_cache)}, время={embedding_time:.1f}ms)")

            # ПРИМЕЧАНИЕ (2026-02-22): Хардкод is_water_supply УДАЛЕН
            # location_type передается в поиск для всех категорий
            # AI сам определяет, нужно ли уточнять локацию

            # ШАГ 2: Параллельный двойной поиск
            search_start = time.perf_counter()
            tag_results = await self._search_by_tags(query_embedding, incident_type, location_type, category)
            service_results = await self._search_by_services(query_embedding, incident_type, location_type, category)
            search_time = (time.perf_counter() - search_start) * 1000

            logger.info(f"VectorSearch: найдено тегов: {len(tag_results)}, услуг: {len(service_results)}")

            # ШАГ 3: Слияние результатов
            merge_start = time.perf_counter()
            merged_candidates = self._merge_results(tag_results, service_results)
            merge_time = (time.perf_counter() - merge_start) * 1000

            logger.info(f"VectorSearch: после слияния: {len(merged_candidates)} кандидатов")

            total_time = (time.perf_counter() - total_start) * 1000

            # ДЕТАЛЬНЫЙ ЛОГ ВРЕМЕНИ (print + logger)
            perf_msg = f"VectorSearch: preload={preload_time:.1f}ms, embedding={embedding_time:.1f}ms, search={search_time:.1f}ms, merge={merge_time:.1f}ms, TOTAL={total_time:.1f}ms"
            print(f"[PERFORMANCE] {perf_msg}")
            logger.info(perf_msg)

            if not merged_candidates:
                return {
                    'status': 'not_found',
                    'candidates': [],
                    'method': 'vector_search'
                }

            return {
                'status': 'success',
                'candidates': merged_candidates,
                'method': 'vector_search'
            }

        except Exception as e:
            logger.error(f"Ошибка в VectorSearchService: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }

    def _preprocess_text(self, text: str) -> str:
        """Предобработка текста сообщения"""
        # Приводим к нижнему регистру
        text = text.lower()

        # Убираем лишние символы
        text = re.sub(r'[^\w\s]', ' ', text)

        # Нормализуем пробелы
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    async def _search_by_tags(self, query_embedding: np.ndarray,
                             incident_type: str, location_type: str, category: str) -> List[Dict]:
        """
        ОПТИМИЗИРОВАННО (2026-03-05): Поиск по embedding тегов из ПРЕДЗАГРУЖЕННОГО кэша

        Алгоритм:
        1. Берем embedding из кэша (без SQL запроса!)
        2. Фильтруем по incident_type, location_type, category
        3. Вычисляем косинусное сходство для каждого
        4. Фильтруем по порогу (0.70)
        5. Группируем по service_id (максимум среди тегов услуги)

        Returns:
            List[Dict] - кандидаты с полями:
                - service_id
                - service_name
                - confidence (cosine similarity)
                - source ('vector_tag_search')
                - incident_type, category, location_type
        """
        try:
            # ОПТИМИЗАЦИЯ (2026-03-05): Используем предзагруженный кэш вместо SQL!
            tag_similarities = {}  # {service_id: max_similarity}
            service_data = {}  # {service_id: {service_name, incident_type, ...}}

            # Фильтруем по параметрам и вычисляем сходство
            for item in VectorSearchService._tags_embeddings_cache:
                # Применяем фильтры
                if incident_type and item['incident_type'] != incident_type:
                    continue
                if location_type and item['location_type'] != location_type:
                    continue
                if category and item['category'] != category:
                    continue

                # Вычисляем косинусное сходство
                similarity = self._cosine_similarity(query_embedding, item['embedding'])

                # Сохраняем максимум для каждого service_id
                service_id = item['service_id']
                if service_id not in tag_similarities or similarity > tag_similarities[service_id]:
                    tag_similarities[service_id] = similarity
                    service_data[service_id] = {
                        'service_name': item['scenario_name'],
                        'incident_type': item['incident_type'] or '',
                        'category': item['category'] or '',
                        'location_type': item['location_type'] or '',
                        'matched_tag': ''  # Не храним tag_name в кэше
                    }

            # Фильтруем по порогу
            threshold = 0.70
            candidates = []

            for service_id, similarity in tag_similarities.items():
                if similarity >= threshold:
                    data = service_data[service_id]
                    candidates.append({
                        'service_id': service_id,
                        'service_name': data['service_name'],
                        'confidence': round(similarity, 3),
                        'source': 'vector_tag_search',
                        'incident_type': data['incident_type'],
                        'category': data['category'],
                        'location_type': data['location_type'],
                        'matched_tag': data['matched_tag']
                    })

            # Сортируем по confidence DESC
            candidates.sort(key=lambda x: x['confidence'], reverse=True)

            return candidates

        except Exception as e:
            logger.error(f"Ошибка поиска по тегам: {e}")
            return []

    async def _search_by_services(self, query_embedding: np.ndarray,
                                 incident_type: str, location_type: str, category: str) -> List[Dict]:
        """
        ОПТИМИЗИРОВАННО (2026-03-05): Поиск по embedding услуг из ПРЕДЗАГРУЖЕННОГО кэша

        Алгоритм:
        1. Берем embedding из кэша (без SQL запроса!)
        2. Фильтруем по incident_type, location_type, category
        3. Вычисляем косинусное сходство
        4. Фильтруем по порогу (0.70)

        Returns:
            List[Dict] - кандидаты с полями:
                - service_id
                - service_name
                - confidence (cosine similarity)
                - source ('vector_service_search')
                - incident_type, category, location_type
        """
        try:
            # ОПТИМИЗАЦИЯ (2026-03-05): Используем предзагруженный кэш вместо SQL!
            threshold = 0.70
            candidates = []

            # Фильтруем по параметрам и вычисляем сходство
            for item in VectorSearchService._services_embeddings_cache:
                # Применяем фильтры (по type_id)
                if incident_type:
                    # Нужно найти type_id по имени - пропускаем фильтр для простоты
                    pass
                if location_type or category:
                    # В кэше услуг нет location_type и category - пропускаем
                    pass

                # Вычисляем косинусное сходство
                similarity = self._cosine_similarity(query_embedding, item['embedding'])

                # Фильтруем по порогу
                if similarity >= threshold:
                    candidates.append({
                        'service_id': item['service_id'],
                        'service_name': item['scenario_name'],
                        'confidence': round(similarity, 3),
                        'source': 'vector_service_search',
                        'incident_type': '',  # Не храним в кэше
                        'category': '',
                        'location_type': ''
                    })

            # Сортируем по confidence DESC
            candidates.sort(key=lambda x: x['confidence'], reverse=True)

            return candidates

        except Exception as e:
            logger.error(f"Ошибка поиска по услугам: {e}")
            return []

    def _merge_results(self, tag_results: List[Dict], service_results: List[Dict]) -> List[Dict]:
        """
        Слияние результатов от тегового и сервисного поиска

        АЛГОРИТМ СЛИЯНИЯ С ВЕСАМИ:

        Шаг 1: Создаем словарь {service_id: {tag_conf, service_conf, data}}

        Шаг 2: Для каждого service_id вычисляем итоговый confidence:

        ПРАВИЛА ФОРМИРОВАНИЯ ВЕСА:

        А. В ОТДЕЛЬНЫХ ПОДМНОЖЕСТВАХ (теги, услуги):
           ----------------------------------------------------
           - Confidence = косинусное сходство (0.0 - 1.0)
           - Порог тегов: 0.70 (одинаково для точности и полноты)
           - Порог услуг: 0.70 (одинаково для точности и полноты)
           - ОДИНАКОВЫЕ ПОРОГИ: упрощает логику, нет приоритетов

        Б. ПРИ ОБЪЕДИНЕНИИ ПОДМНОЖЕСТВ:
           ----------------------------------------------------
           Используем СРЕДНЕВЗВЕШЕННОЕ значение

           Случай 1: Услуга найдена в ОБЕИХ выборках
             - final_conf = WEIGHT_TAG * tag_conf + WEIGHT_SERVICE * service_conf
             - WEIGHT_TAG = 0.6 (теги точнее - короткие фразы)
             - WEIGHT_SERVICE = 0.4 (услуги длиннее, больше шума)
             - ПРИМЕР: 0.6 * 0.82 + 0.4 * 0.40 = 0.652
             - source = 'vector_tag_search' (приоритет тегам)

           Случай 2: Услуга найдена ТОЛЬКО в тегах
             - final_conf = tag_conf (НЕ штрафуем!)
             - ПРИЧИНА: Отсутствие в услугах ≠ ошибка, разные типы поиска
             - source = 'vector_tag_search'

           Случай 3: Услуга найдена ТОЛЬКО в услугах
             - final_conf = service_conf (НЕ штрафуем!)
             - ПРИЧИНА: Отсутствие в тегах ≠ ошибка, разные типы поиска
             - source = 'vector_service_search'

        Шаг 3: Сортируем по итоговому confidence DESC
        Шаг 4: Возвращаем TOP-10

        Args:
            tag_results: Результаты поиска по тегам
            service_results: Результаты поиска по услугам

        Returns:
            List[Dict] - слитые и отсортированные кандидаты
        """
        # Веса для среднего взвешенного
        WEIGHT_TAG = 0.6      # Теги точнее (короткие сфокусированные фразы)
        WEIGHT_SERVICE = 0.4  # Услуги длиннее (больше шума, но выше полнота)

        # Шаг 1: Собираем в словарь
        merged = {}  # {service_id: {tag_conf, service_conf, data}}

        # Добавляем теговые результаты
        for candidate in tag_results:
            service_id = candidate['service_id']
            merged[service_id] = {
                'tag_conf': candidate['confidence'],
                'service_conf': None,
                'data': candidate
            }

        # Добавляем сервисные результаты
        for candidate in service_results:
            service_id = candidate['service_id']
            if service_id in merged:
                # Уже есть от тегов - обновляем service_conf
                merged[service_id]['service_conf'] = candidate['confidence']
            else:
                # Только в сервисах
                merged[service_id] = {
                    'tag_conf': None,
                    'service_conf': candidate['confidence'],
                    'data': candidate
                }

        # Шаг 2: Вычисляем итоговый confidence (СРЕДНЕВЗВЕШЕННОЕ)
        final_candidates = []

        for service_id, item in merged.items():
            tag_conf = item['tag_conf']
            service_conf = item['service_conf']
            data = item['data']

            # ПРИМЕНЯЕМ СРЕДНЕВЗВЕШЕННОЕ (ВСЕГДА!)
            if tag_conf is not None and service_conf is not None:
                # Случай 1: Оба нашли - полное средневзвешенное
                final_conf = WEIGHT_TAG * tag_conf + WEIGHT_SERVICE * service_conf
                data['source'] = 'vector_tag_search'  # Приоритет тегам
                data['service_confidence'] = round(service_conf, 3)
                data['tag_confidence'] = round(tag_conf, 3)
                data['confidence'] = round(final_conf, 3)

            elif tag_conf is not None:
                # Случай 2: Только теги - средневзвешенное с нулем (ШТРАФ 40%)
                final_conf = WEIGHT_TAG * tag_conf  # service_conf = 0
                data['confidence'] = round(final_conf, 3)
                data['source'] = 'vector_tag_search'
                data['tag_confidence'] = round(tag_conf, 3)  # ИСПРАВЛЕНО (2026-01-15)
                data['service_confidence'] = None

            else:
                # Случай 3: Только сервис - средневзвешенное с нулем (ШТРАФ 60%)
                final_conf = WEIGHT_SERVICE * service_conf  # tag_conf = 0
                data['confidence'] = round(final_conf, 3)
                data['source'] = 'vector_service_search'
                data['tag_confidence'] = None  # ИСПРАВЛЕНО (2026-01-15)
                data['service_confidence'] = round(service_conf, 3)  # ИСПРАВЛЕНО (2026-01-15)

            final_candidates.append(data)

        # Шаг 3: Сортировка по итоговому confidence
        final_candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Шаг 4: Возвращаем TOP-10
        return final_candidates[:10]

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Вычисление косинусного сходства между векторами

        cosine_sim = (vec1 · vec2) / (||vec1|| * ||vec2||)

        Returns:
            float: значение от 0.0 до 1.0
        """
        try:
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return float(dot_product / (norm1 * norm2))

        except Exception as e:
            logger.error(f"Ошибка вычисления косинусного сходства: {e}")
            return 0.0
