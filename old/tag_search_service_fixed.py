#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TagSearchService Fixed - микросервис поиска услуг по тегам для реальной БД
Адаптирован под структуру services_catalog
"""

import logging
import re
from typing import List, Dict, Any
from django.db import connection

from asgiref.sync import sync_to_async
import pymorphy2

logger = logging.getLogger(__name__)


class TagSearchServiceFixed:
    """Микросервис поиска услуг по тегам для реальной структуры БД"""

    def __init__(self):
        self.service_cache = None
        self.morph = None
        logger.info("TagSearchServiceFixed инициализирован для services_catalog")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    async def _load_services(self):
        """Асинхронная загрузка услуг из services_catalog"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Загружаем услуги из services_catalog
                    cursor.execute("""
                        SELECT service_id, scenario_name, description_for_search,
                               category_id, object_id, type_id, kind_id
                        FROM services_catalog
                        WHERE is_active = TRUE
                        ORDER BY service_id
                    """)
                    services = cursor.fetchall()

                    service_cache = {}
                    for service_id, scenario_name, description_for_search, category_id, object_id, type_id, kind_id in services:
                        service_cache[service_id] = {
                            'name': scenario_name,
                            'description': description_for_search or '',
                            'category_id': category_id,
                            'object_id': object_id,
                            'type_id': type_id,
                            'kind_id': kind_id,
                            'tags': []
                        }

                        # Извлекаем ключевые слова из описания для поиска
                        if description_for_search:
                            # Простая токенизация по запятым и пробелам
                            tags = []
                            for word in re.findall(r'\b\w+\b', description_for_search.lower()):
                                if len(word) > 2:  # Пропускаем слишком короткие слова
                                    tags.append(word)
                            service_cache[service_id]['tags'] = list(set(tags))  # Убираем дубликаты

                    # Загружаем связанные теги из service_tags + ref_tags
                    cursor.execute("""
                        SELECT sc.service_id, rt.tag_name, COALESCE(st.tag_weight, 1.0) as weight
                        FROM services_catalog sc
                        LEFT JOIN service_tags st ON sc.service_id = st.service_id
                        LEFT JOIN ref_tags rt ON st.tag_id = rt.tag_id
                        WHERE sc.is_active = TRUE AND rt.tag_name IS NOT NULL
                        ORDER BY sc.service_id, st.tag_weight DESC
                    """)
                    tags = cursor.fetchall()

                    for service_id, tag_name, weight in tags:
                        if service_id in service_cache:
                            service_cache[service_id]['tags'].append(tag_name.lower())

                    # Убираем дубликаты тегов
                    for service_id in service_cache:
                        service_cache[service_id]['tags'] = list(set(service_cache[service_id]['tags']))

                    return service_cache

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"Загружено {len(self.service_cache)} услуг в кэш TagSearchServiceFixed")
            return self.service_cache

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг в TagSearchServiceFixed: {e}")
            return {}

    async def search_services(self, message_text: str) -> Dict[str, Any]:
        """
        Поиск услуг по тексту сообщения с помощью нечеткого matching
        """
        try:
            if not self.service_cache:
                await self._load_services()

            if not self.service_cache:
                return {
                    'status': 'error',
                    'message': 'Не удалось загрузить услуги',
                    'candidates': []
                }

            # Подготовка текста для поиска
            search_tokens = self._extract_search_tokens(message_text)
            morph = self._get_morph()

            # Нормализация токенов
            normalized_tokens = []
            for token in search_tokens:
                normalized = token.lower()
                # Морфологическая нормализация
                normal_forms = morph.parse(normalized)
                if normal_forms:
                    normalized = normal_forms[0].normal_form
                normalized_tokens.append(normalized)

            logger.info(f"Токены для поиска: {normalized_tokens}")

            candidates = []

            # Поиск по каждому сервису в кэше
            for service_id, service_data in self.service_cache.items():
                score = self._calculate_match_score(normalized_tokens, service_data, morph)

                if score > 0.3:  # Порог уверенности
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service_data['name'],
                        'confidence': score,
                        'source': 'tag_search_fixed'
                    })

            # Сортировка по уверенности
            candidates.sort(key=lambda x: x['confidence'], reverse=True)

            logger.info(f"TagSearchServiceFixed найдено кандидатов: {len(candidates)}")
            for cand in candidates[:3]:
                logger.info(f"  - {cand['service_name']}: {cand['confidence']:.3f}")

            return {
                'status': 'success',
                'candidates': candidates,
                'method': 'tag_search_fixed'
            }

        except Exception as e:
            logger.error(f"Ошибка в TagSearchServiceFixed.search_services: {e}")
            return {
                'status': 'error',
                'message': f'Ошибка поиска: {str(e)}',
                'candidates': []
            }

    def _extract_search_tokens(self, text: str) -> List[str]:
        """Извлечение значимых токенов из текста"""
        # Удаление пунктуации и разделение на слова
        words = re.findall(r'\b[а-яё\w]+\b', text.lower())

        # Фильтрация стоп-слов
        stop_words = {
            'и', 'в', 'на', 'с', 'по', 'для', 'от', 'из', 'к', 'о', 'об', 'у', 'а', 'но', 'да',
            'что', 'как', 'где', 'когда', 'почему', 'зачем', 'какой', 'какая', 'какое', 'какие',
            'мой', 'моя', 'моё', 'мои', 'я', 'меня', 'мне', 'ты', 'вы', 'вы', 'вас', 'вам',
            'есть', 'быть', 'был', 'была', 'было', 'будет', 'есть', 'нет', 'не', 'ни'
        }

        return [word for word in words if len(word) > 2 and word not in stop_words]

    def _calculate_match_score(self, search_tokens: List[str], service_data: Dict, morph) -> float:
        """Расчет оценки совпадения токенов с услугой"""
        score = 0.0

        # Теги услуги
        service_tags = [tag.lower() for tag in service_data.get('tags', [])]
        service_name = service_data.get('name', '').lower()
        service_description = service_data.get('description', '').lower()

        # Прямое совпадение токенов
        for token in search_tokens:
            # Поиск в названии (вес выше)
            if token in service_name:
                score += 0.4
                logger.debug(f"Прямое совпадение в названии: {token} в {service_name}")

            # Поиск в описании
            if token in service_description:
                score += 0.2

            # Прямой поиск в тегах
            if service_tags:
                for tag in service_tags:
                    if token in tag or tag in token:
                        score += 0.2
                        logger.debug(f"Совпадение в тегах: {token} ~ {tag}")

        # Бонус за полные совпадения фраз
        combined_search = ' '.join(search_tokens)
        if combined_search in service_name:
            score += 0.5
        elif combined_search in service_description:
            score += 0.3

        return min(score, 1.0)  # Ограничиваем максимальную оценку