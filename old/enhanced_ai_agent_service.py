#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EnhancedAIAgentService - улучшенный AI микросервис с фильтрацией каталога
Использует предварительную фильтрацию и структурированные данные для YandexGPT
import os
"""

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional
from django.db import connection
from asgiref.sync import sync_to_async
from intelligent_filter_service import IntelligentFilterService

logger = logging.getLogger(__name__)


class EnhancedAIAgentService:
    """Улучшенный микросервис AI-анализа с фильтрацией"""

    def __init__(self):
        self.service_cache = None
        self.filter_service = IntelligentFilterService()
        self.api_key = os.getenv("YANDEX_API_KEY", "")
        self.folder_id = os.getenv("YANDEX_FOLDER_ID", "")
        logger.info("EnhancedAIAgentService инициализирован с IntelligentFilter")

    async def _load_services(self):
        """Загрузка услуг с их атрибутами"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT sc.service_id as id, sc.scenario_name as name,
                               rc.category_name as category, sc.object_type,
                               sc.incident_type, sc.location_type, sc.tags, sc.keywords,
                               sc.description
                        FROM services_catalog sc
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        WHERE sc.is_active = TRUE
                    """)
                    results = cursor.fetchall()

                services = []
                for row in results:
                    (service_id, name, category, object_type, incident_type,
                     location_type, tags, keywords, description) = row

                    services.append({
                        'id': service_id,
                        'name': name,
                        'category': category or '',
                        'object_type': object_type or '',
                        'incident_type': incident_type or '',
                        'location_type': location_type or '',
                        'tags': tags or '',
                        'keywords': keywords or '',
                        'description': description or ''
                    })

                return services

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"EnhancedAIAgent: загружено {len(self.service_cache)} услуг с атрибутами")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = []

    async def search(self, message_text: str) -> Dict:
        """
        Основной метод поиска с интеллектуальной фильтрацией

        Args:
            message_text: Текст сообщения пользователя

        Returns:
            Dict: Результат в формате JSON
        """
        try:
            logger.info(f"EnhancedAIAgent: анализ текста '{message_text}'")

            if self.service_cache is None:
                await self._load_services()

            if not self.service_cache:
                return {'candidates': [], 'error': 'Услуги не загружены'}

            # 1. Интеллектуальная фильтрация каталога
            filter_result = await self.filter_service.analyze_request(message_text)
            filtered_service_ids = filter_result.get('filtered_service_ids', [])

            # 2. Формируем отфильтрованный каталог
            relevant_services = self._get_relevant_services(filtered_service_ids, filter_result)

            if not relevant_services:
                logger.info("EnhancedAIAgent: нет релевантных услуг после фильтрации")
                return {'candidates': [], 'error': 'Нет релевантных услуг'}

            # 3. Создаем структурированный промпт
            prompt = self._create_enhanced_prompt(message_text, relevant_services, filter_result)

            # 4. Вызываем YandexGPT
            response = await self._call_yandex_gpt(prompt)

            # 5. Парсим ответ
            result = self._parse_ai_response(response)

            # 6. Добавляем метаданные
            if result.get('candidates'):
                for candidate in result['candidates']:
                    candidate['source'] = 'enhanced_ai'
                    candidate['filter_context'] = filter_result.get('filters', {})

            logger.info(f"EnhancedAIAgent: найдено {len(result.get('candidates', []))} кандидатов")
            return result

        except Exception as e:
            logger.error(f"Ошибка в EnhancedAIAgentService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }

    def _get_relevant_services(self, filtered_service_ids: List[int], filter_result: Dict) -> List[Dict]:
        """
        Получение релевантных услуг с учетом фильтрации

        Args:
            filtered_service_ids: ID услуг отфильтрованных
            filter_result: Результаты фильтрации

        Returns:
            List[Dict]: Список релевантных услуг
        """
        if not filtered_service_ids:
            # Если фильтрация не дала результатов, возвращаем все (fallback)
            return self.service_cache

        # Возвращаем только отфильтрованные услуги
        relevant_services = []
        for service in self.service_cache:
            if service['id'] in filtered_service_ids:
                relevant_services.append(service)

        # Если слишком мало услуг, добавляем похожие по категории
        if len(relevant_services) < 3:
            relevant_services = self._expand_relevant_services(relevant_services, filter_result)

        return relevant_services

    def _expand_relevant_services(self, base_services: List[Dict], filter_result: Dict) -> List[Dict]:
        """
        Расширение набора релевантных услуг

        Args:
            base_services: Базовый набор услуг
            filter_result: Результаты фильтрации

        Returns:
            List[Dict]: Расширенный набор услуг
        """
        expanded = base_services.copy()

        # Добавляем услуги из тех же категорий
        base_categories = {s['category'] for s in base_services if s['category']}
        base_incident_types = {s['incident_type'] for s in base_services if s['incident_type']}

        for service in self.service_cache:
            if service not in expanded:
                # Добавляем если совпадает категория или тип инцидента
                if (service['category'] in base_categories or
                    service['incident_type'] in base_incident_types):
                    expanded.append(service)

        return expanded[:10]  # Ограничиваем максимум 10 услугами для промпта

    def _create_enhanced_prompt(self, message_text: str, services: List[Dict], filter_result: Dict) -> str:
        """
        Создание улучшенного промпта с фильтрацией и структурированными данными

        Args:
            message_text: Текст сообщения пользователя
            services: Отфильтрованный список услуг
            filter_result: Результаты интеллектуальной фильтрации

        Returns:
            str: Структурированный промпт для YandexGPT
        """
        # Структурируем услуги в JSON
        services_json = []
        for service in services:
            services_json.append({
                "id": service['id'],
                "name": service['name'],
                "category": service['category'],
                "object_type": service['object_type'],
                "incident_type": service['incident_type'],
                "location_type": service['location_type'],
                "tags": service['tags'],
                "keywords": service['keywords']
            })

        # Получаем фильтры
        filters = filter_result.get('filters', {})
        problem_category = filters.get('problem_category', {})
        location_type = filters.get('location_type', {})
        utility_system = filters.get('utility_system', {})

        prompt = f"""
Ты - эксперт по ЖКХ услугам. Проанализируй обращение пользователя с учетом контекстной фильтрации.

## Анализ контекста:
- Тип инцидента: {filters.get('incident_type', {}).get('type', 'unknown')}
- Категория проблемы: {problem_category.get('category', 'unknown')}
- Локализация: {location_type.get('type', 'unknown')}
- Система коммуникаций: {utility_system.get('system', 'unknown')}
- Уровень срочности: {filters.get('urgency_level', {}).get('level', 'medium')}

## Классификаторы:
- category: категория услуги (водопроводные, электрические, отопительные и т.д.)
- object_type: тип объекта (квартира, подъезд, подвал и т.д.)
- incident_type: тип инцидента (инцидент, запрос, консультация)
- location_type: тип локации (внутри, общее)
- tags: ключевые теги для точного определения
- keywords: дополнительные ключевые слова

## Релевантные услуги (отфильтрованный каталог):
{json.dumps(services_json, ensure_ascii=False, indent=2)}

## Обращение пользователя:
"{message_text}"

## Инструкции:
1. Проанализируй текст и контекст
2. Выбери наиболее подходящую услугу из предложенного списка
3. Учти, что каталог уже отфильтрован по релевантности
4. Верни только JSON с результатом

Формат ответа:
{{
    "service_id": <ID_услуги>,
    "confidence": <уверенность_от_0_до_1>,
    "reason": "<обоснование выбора>",
    "alternative_services": [<ID_альтернативных_услуг>],
    "needs_clarification": <true/false>,
    "clarification_type": "<тип_уточнения>"
}}

Правила:
- Если уверенность ниже 0.6, укажи needs_clarification: true
- service_id должен быть точным ID из списка выше
- alternative_services - ID подходящих альтернативных вариантов
- reason - объяснение выбора с учетом контекста

JSON:"""

        return prompt

    async def _call_yandex_gpt(self, prompt: str) -> str:
        """Вызов YandexGPT API с улучшенной конфигурацией"""
        try:
            import aiohttp

            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "x-folder-id": self.folder_id,
                "Content-Type": "application/json"
            }

            data = {
                "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite/latest",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.2,  # Снижаем для более детерминированных ответов
                    "maxTokens": 500      # Увеличиваем для детальных ответов
                },
                "messages": [
                    {
                        "role": "system",
                        "text": "Ты - профессиональный аналитик ЖКХ услуг с глубоким пониманием технических аспектов и классификаторов."
                    },
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['result']['alternatives'][0]['message']['text']
                    else:
                        error_text = await response.text()
                        logger.error(f"YandexGPT API error: {response.status} - {error_text}")
                        return None

        except Exception as e:
            logger.error(f"Ошибка вызова YandexGPT: {e}")
            return None

    def _parse_ai_response(self, response_text: str) -> Dict:
        """Парсинг улучшенного ответа от ИИ"""
        try:
            if not response_text:
                return {'candidates': [], 'status': 'no_response'}

            # Ищем JSON в ответе
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                logger.warning(f"Не найден JSON в ответе: {response_text}")
                return {'candidates': [], 'status': 'no_json_found'}

            json_text = response_text[start_idx:end_idx]
            parsed_data = json.loads(json_text)

            service_id = parsed_data.get('service_id')
            confidence = parsed_data.get('confidence', 0.0)
            reason = parsed_data.get('reason', '')
            alternative_ids = parsed_data.get('alternative_services', [])
            needs_clarification = parsed_data.get('needs_clarification', False)
            clarification_type = parsed_data.get('clarification_type', '')

            if service_id is None:
                # Если ИИ не определил услугу, возвращаем пустой результат
                return {
                    'candidates': [],
                    'status': 'no_service_identified',
                    'needs_clarification': needs_clarification,
                    'clarification_type': clarification_type,
                    'ai_reasoning': reason
                }

            # Ищем услуги в кэше
            candidates = []
            for service in self.service_cache:
                if service['id'] == service_id:
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service['name'],
                        'confidence': max(0.0, min(1.0, float(confidence))),
                        'source': 'enhanced_ai',
                        'ai_reasoning': reason,
                        'needs_clarification': needs_clarification,
                        'clarification_type': clarification_type
                    })
                    break

            # Добавляем альтернативные услуги
            alternative_candidates = []
            for alt_id in alternative_ids:
                for service in self.service_cache:
                    if service['id'] == alt_id:
                        alternative_candidates.append({
                            'service_id': alt_id,
                            'service_name': service['name'],
                            'confidence': confidence * 0.8,  # Альтернативы с меньшей уверенностью
                            'source': 'enhanced_ai_alternative',
                            'ai_reasoning': f"Альтернатива: {reason}"
                        })
                        break

            candidates.extend(alternative_candidates)

            return {
                'status': 'success',
                'candidates': candidates[:3],  # Максимум 3 кандидата
                'ai_reasoning': reason,
                'needs_clarification': needs_clarification,
                'clarification_type': clarification_type,
                'alternatives_count': len(alternative_candidates)
            }

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return {
                'candidates': [],
                'status': 'json_parse_error',
                'raw_response': response_text
            }
        except Exception as e:
            logger.error(f"Ошибка обработки ответа ИИ: {e}")
            return {
                'candidates': [],
                'status': 'processing_error',
                'error': str(e)
            }