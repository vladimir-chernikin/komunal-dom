#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VectorSearchService - микросервис векторного поиска услуг
Использует Yandex Embeddings API для семантического поиска

РЕФАКТОРИНГ (2026-01-13):
- Двойной поиск: по embedding тегов (точность) + embedding услуг (полнота)
- Фильтрация в SQL WHERE (incident_type, location_type, category)
- Слияние результатов с адаптивными весами
"""

import logging
import re
import numpy as np
from typing import List, Dict, Set, Tuple
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class VectorSearchService:
    """Микросервис векторного поиска услуг с двойным поиском"""

    def __init__(self):
        logger.info("VectorSearchService инициализирован (двойной векторный поиск)")

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод векторного поиска с двойным поиском

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

            # ШАГ 1: Получаем embedding запроса
            from ai_agent_service import AIAgentService
            ai_service = AIAgentService(provider='yandexgpt')

            try:
                query_embedding, _ = await ai_service.get_embedding(message_clean)
                query_embedding = np.array(query_embedding, dtype=np.float32)
            except Exception as e:
                logger.error(f"Не удалось получить embedding запроса: {e}")
                return {
                    'status': 'error',
                    'error': f'Не удалось получить embedding: {str(e)}',
                    'candidates': []
                }

            # ШАГ 2: Параллельный двойной поиск
            tag_results = await self._search_by_tags(query_embedding, incident_type, location_type, category)
            service_results = await self._search_by_services(query_embedding, incident_type, location_type, category)

            logger.info(f"VectorSearch: найдено тегов: {len(tag_results)}, услуг: {len(service_results)}")

            # ШАГ 3: Слияние результатов
            merged_candidates = self._merge_results(tag_results, service_results)

            logger.info(f"VectorSearch: после слияния: {len(merged_candidates)} кандидатов")

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
        Поиск по embedding тегов

        Алгоритм:
        1. Загружаем embedding тегов с фильтрами
        2. Вычисляем косинусное сходство для каждого
        3. Фильтруем по порогу (0.75)
        4. Группируем по service_id (максимум среди тегов услуги)

        Returns:
            List[Dict] - кандидаты с полями:
                - service_id
                - service_name
                - confidence (cosine similarity)
                - source ('vector_tag_search')
                - incident_type, category, location_type
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # Загружаем embedding тегов с фильтрами
                    cursor.execute("""
                        SELECT
                            st.service_id,
                            sc.scenario_name as service_name,
                            COALESCE(rst.type_name, '') as incident_type,
                            COALESCE(rc.category_name, '') as category,
                            COALESCE(rl.localization_name, '') as location_type,
                            rt.tag_id,
                            rt.embedding_tag,
                            rt.tag_name
                        FROM service_tags st
                        JOIN services_catalog sc ON st.service_id = sc.service_id
                        JOIN ref_tags rt ON st.tag_id = rt.tag_id
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                          AND rt.is_active = TRUE
                          AND rt.embedding_tag IS NOT NULL
                          AND (%s = '' OR rst.type_name = %s)
                          AND (%s = '' OR rl.localization_name = %s)
                          AND (%s = '' OR rc.category_name = %s)
                    """, [incident_type, incident_type,
                          location_type, location_type,
                          category, category])

                    rows = cursor.fetchall()

                # Вычисляем косинусное сходство
                tag_similarities = {}  # {service_id: max_similarity}
                service_data = {}  # {service_id: {service_name, incident_type, ...}}

                for row in rows:
                    service_id = row[0]
                    service_name = row[1]
                    db_incident_type = row[2]  # ИСПРАВЛЕНО: переименовано
                    cat = row[3]
                    loc_type = row[4]
                    tag_id = row[5]
                    embedding_json = row[6]
                    tag_name = row[7]

                    # Парсим embedding из JSONB
                    try:
                        tag_embedding = np.array(eval(embedding_json), dtype=np.float32)
                    except:
                        continue

                    # Вычисляем косинусное сходство
                    similarity = self._cosine_similarity(query_embedding, tag_embedding)

                    # Сохраняем максимум для каждого service_id
                    if service_id not in tag_similarities or similarity > tag_similarities[service_id]:
                        tag_similarities[service_id] = similarity
                        service_data[service_id] = {
                            'service_name': service_name,
                            'incident_type': db_incident_type or '',
                            'category': cat or '',
                            'location_type': loc_type or '',
                            'matched_tag': tag_name
                        }

                # Фильтруем по порогу (одинаково для тегов и услуг)
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

            return await sync_to_async(search_sync)()

        except Exception as e:
            logger.error(f"Ошибка поиска по тегам: {e}")
            return []

    async def _search_by_services(self, query_embedding: np.ndarray,
                                 incident_type: str, location_type: str, category: str) -> List[Dict]:
        """
        Поиск по embedding услуг

        Алгоритм:
        1. Загружаем embedding услуг с фильтрами
        2. Вычисляем косинусное сходство
        3. Фильтруем по порогу (0.70)

        Returns:
            List[Dict] - кандидаты с полями:
                - service_id
                - service_name
                - confidence (cosine similarity)
                - source ('vector_service_search')
                - incident_type, category, location_type
        """
        try:
            def search_sync():
                with connection.cursor() as cursor:
                    # Загружаем embedding услуг с фильтрами
                    cursor.execute("""
                        SELECT
                            sc.service_id,
                            sc.scenario_name as service_name,
                            COALESCE(rst.type_name, '') as incident_type,
                            COALESCE(rc.category_name, '') as category,
                            COALESCE(rl.localization_name, '') as location_type,
                            sc.embedding_service
                        FROM services_catalog sc
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_localization rl ON sc.localization_id = rl.localization_id
                        WHERE sc.is_active = TRUE
                          AND sc.embedding_service IS NOT NULL
                          AND (%s = '' OR rst.type_name = %s)
                          AND (%s = '' OR rl.localization_name = %s)
                          AND (%s = '' OR rc.category_name = %s)
                    """, [incident_type, incident_type,
                          location_type, location_type,
                          category, category])

                    rows = cursor.fetchall()

                # Вычисляем косинусное сходство
                threshold = 0.70
                candidates = []

                for row in rows:
                    service_id = row[0]
                    service_name = row[1]
                    db_incident_type = row[2]  # ИСПРАВЛЕНО: переименовано
                    cat = row[3]
                    loc_type = row[4]
                    embedding_json = row[5]

                    # Парсим embedding из JSONB
                    try:
                        service_embedding = np.array(eval(embedding_json), dtype=np.float32)
                    except:
                        continue

                    # Вычисляем косинусное сходство
                    similarity = self._cosine_similarity(query_embedding, service_embedding)

                    # Фильтруем по порогу
                    if similarity >= threshold:
                        candidates.append({
                            'service_id': service_id,
                            'service_name': service_name,
                            'confidence': round(similarity, 3),
                            'source': 'vector_service_search',
                            'incident_type': db_incident_type or '',
                            'category': cat or '',
                            'location_type': loc_type or ''
                        })

                # Сортируем по confidence DESC
                candidates.sort(key=lambda x: x['confidence'], reverse=True)

                return candidates

            return await sync_to_async(search_sync)()

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
