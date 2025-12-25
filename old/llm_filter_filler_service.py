#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LLMFilterFillerService - LLM сервис для интеллектуального заполнения фильтров
Использует YandexGPT для заполнения JSON schema с фильтрами услуг
import os
"""

import logging
import json
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class LLMFilterFillerService:
    """LLM сервис для заполнения фильтров услуг"""

    def __init__(self):
        self.api_key = os.getenv("YANDEX_API_KEY", "")
        self.folder_id = os.getenv("YANDEX_FOLDER_ID", "")
        self.catalog_attributes = None
        logger.info("LLMFilterFillerService инициализирован")

    async def _load_catalog_attributes(self):
        """Загрузка уникальных значений атрибутов из services_catalog"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Загружаем уникальные значения для каждого атрибута
                    cursor.execute("""
                        SELECT DISTINCT category FROM services_catalog WHERE category IS NOT NULL AND category != ''
                    """)
                    categories = [row[0] for row in cursor.fetchall()]

                    cursor.execute("""
                        SELECT DISTINCT incident_type FROM services_catalog WHERE incident_type IS NOT NULL AND incident_type != ''
                    """)
                    incident_types = [row[0] for row in cursor.fetchall()]

                    cursor.execute("""
                        SELECT DISTINCT location_type FROM services_catalog WHERE location_type IS NOT NULL AND location_type != ''
                    """)
                    location_types = [row[0] for row in cursor.fetchall()]

                    cursor.execute("""
                        SELECT DISTINCT object_type FROM services_catalog WHERE object_type IS NOT NULL AND object_type != ''
                    """)
                    object_types = [row[0] for row in cursor.fetchall()]

                    # Собираем все теги и ключевые слова
                    cursor.execute("""
                        SELECT tags, keywords FROM services_catalog
                        WHERE tags IS NOT NULL AND keywords IS NOT NULL
                    """)
                    all_tags = set()
                    all_keywords = set()
                    for tags, keywords in cursor.fetchall():
                        if tags:
                            all_tags.update([tag.strip() for tag in tags.split(',')])
                        if keywords:
                            all_keywords.update([kw.strip() for kw in keywords.split(',')])

                    return {
                        'categories': categories,
                        'incident_types': incident_types,
                        'location_types': location_types,
                        'object_types': object_types,
                        'all_tags': list(all_tags)[:50],  # Ограничиваем для промпта
                        'all_keywords': list(all_keywords)[:50]
                    }

            self.catalog_attributes = await sync_to_async(load_sync)()
            logger.info(f"Загружены атрибуты каталога: {len(self.catalog_attributes['categories'])} категорий")

        except Exception as e:
            logger.error(f"Ошибка загрузки атрибутов каталога: {e}")
            self.catalog_attributes = {
                'categories': ['ремонт', 'сантехника', 'отопление', 'лифт', 'коммунальные'],
                'incident_types': ['инцидент', 'запрос', 'консультация'],
                'location_types': ['внутри', 'общее'],
                'object_types': ['квартира', 'подвал', 'лифт', 'счетчики'],
                'all_tags': [],
                'all_keywords': []
            }

    async def fill_filters_from_text(self, text: str, dialog_context: str = "") -> Dict:
        """
        Заполнение фильтров на основе текста диалога с помощью LLM

        Args:
            text: Текущий текст пользователя
            dialog_context: Контекст диалога (предыдущие сообщения)

        Returns:
            Dict: Заполненные фильтры
        """
        try:
            if self.catalog_attributes is None:
                await self._load_catalog_attributes()

            logger.info(f"LLMFilterFiller: анализ текста '{text}'")

            # Создаем промпт с JSON schema
            prompt = self._create_filter_prompt(text, dialog_context)

            # Вызываем YandexGPT
            response = await self._call_llm(prompt)

            # Парсим ответ
            result = self._parse_llm_response(response)

            # Валидируем и дополняем результат
            validated_result = self._validate_filters(result)

            logger.info(f"LLMFilterFiller: заполнено фильтров - {len([k for k, v in validated_result.items() if v])}")
            return validated_result

        except Exception as e:
            logger.error(f"Ошибка в LLMFilterFillerService: {e}")
            return self._get_empty_filters()

    def _create_filter_prompt(self, text: str, dialog_context: str) -> str:
        """Создание промпта для заполнения фильтров"""

        # Формируем доступные значения
        categories_str = ", ".join(self.catalog_attributes['categories'])
        incident_types_str = ", ".join(self.catalog_attributes['incident_types'])
        location_types_str = ", ".join(self.catalog_attributes['location_types'])
        object_types_str = ", ".join(self.catalog_attributes['object_types'])

        prompt = f"""
Ты - эксперт по анализу текста в системе ЖКУ (жилищно-коммунальные услуги).

Проанализируй текст обращения и заполни JSON фильтры на основе ДАННЫХ ИЗ КАТАЛОГА.

## КОНТЕКСТ ДИАЛОГА:
{dialog_context}

## ТЕКУЩИЙ ТЕКСТ ПОЛЬЗОВАТЕЛЯ:
"{text}"

## ДОСТУПНЫЕ ЗНАЧЕНИЯ ИЗ КАТАЛОГА УСЛУГ:
- Категории (category): [{categories_str}]
- Типы инцидентов (incident_type): [{incident_types_str}]
- Типы локаций (location_type): [{location_types_str}]
- Типы объектов (object_type): [{object_types_str}]

## ПРАВИЛА ЗАПОЛНЕНИЯ:
1. Используй ТОЛЬКО значения из доступных списков выше
2. Если уверенность < 90% - оставь поле пустым ("")
3. Не галюцинируй значения, которых нет в каталоге
4. Учитывай весь контекст диалога
5. Для urgency_level используй: low, medium, high, critical
6. Extracted теги только если есть прямое упоминание

## JSON ДЛЯ ЗАПОЛНЕНИЯ:
{{
    "category": "выбранная категория или ''",
    "incident_type": "выбранный тип инцидента или ''",
    "location_type": "выбранный тип локации или ''",
    "object_type": "выбранный тип объекта или ''",
    "urgency_level": "low/medium/high/critical",
    "extracted_tags": ["тег1", "тег2"],
    "confidence_scores": {{
        "category": 0.95,
        "incident_type": 0.80,
        "location_type": 0.0,
        "object_type": 0.0
    }},
    "reasoning": "объяснение выбора фильтров"
}}

Верни ТОЛЬКО JSON без дополнительных текстов."""

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Вызов LLM модели"""
        try:
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
                    "temperature": 0.1,  # Низкая температура для детерминированности
                    "maxTokens": 300
                },
                "messages": [
                    {
                        "role": "system",
                        "text": "Ты - профессиональный аналитический ассистент для ЖКУ услуг."
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

    def _parse_llm_response(self, response_text: str) -> Dict:
        """Парсинг LLM ответа"""
        try:
            if not response_text:
                return self._get_empty_filters()

            # Ищем JSON в ответе
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                logger.warning(f"Не найден JSON в ответе LLM: {response_text}")
                return self._get_empty_filters()

            json_text = response_text[start_idx:end_idx]
            parsed_data = json.loads(json_text)

            return parsed_data

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON от LLM: {e}")
            return self._get_empty_filters()
        except Exception as e:
            logger.error(f"Ошибка обработки ответа LLM: {e}")
            return self._get_empty_filters()

    def _validate_filters(self, filters: Dict) -> Dict:
        """Валидация и коррекция фильтров"""
        if not self.catalog_attributes:
            return filters

        validated = {}

        # Проверяем category
        category = filters.get('category', '')
        if category and category in self.catalog_attributes['categories']:
            validated['category'] = category
        else:
            validated['category'] = ''

        # Проверяем incident_type
        incident_type = filters.get('incident_type', '')
        if incident_type and incident_type in self.catalog_attributes['incident_types']:
            validated['incident_type'] = incident_type
        else:
            validated['incident_type'] = ''

        # Проверяем location_type
        location_type = filters.get('location_type', '')
        if location_type and location_type in self.catalog_attributes['location_types']:
            validated['location_type'] = location_type
        else:
            validated['location_type'] = ''

        # Проверяем object_type
        object_type = filters.get('object_type', '')
        if object_type and object_type in self.catalog_attributes['object_types']:
            validated['object_type'] = object_type
        else:
            validated['object_type'] = ''

        # Копируем остальные поля
        validated['urgency_level'] = filters.get('urgency_level', 'medium')
        validated['extracted_tags'] = filters.get('extracted_tags', [])
        validated['confidence_scores'] = filters.get('confidence_scores', {})
        validated['reasoning'] = filters.get('reasoning', '')

        return validated

    def _get_empty_filters(self) -> Dict:
        """Возвращает пустую структуру фильтров"""
        return {
            'category': '',
            'incident_type': '',
            'location_type': '',
            'object_type': '',
            'urgency_level': 'medium',
            'extracted_tags': [],
            'confidence_scores': {},
            'reasoning': 'Не удалось заполнить фильтры'
        }

    async def get_filtered_service_ids(self, filters: Dict) -> List[int]:
        """Получение ID услуг по фильтрам"""
        try:
            def filter_sync():
                with connection.cursor() as cursor:
                    # Базовый запрос
                    query = "SELECT DISTINCT service_id FROM services_catalog WHERE is_active = TRUE"
                    params = []

                    # Добавляем фильтры если они заполнены
                    if filters.get('category'):
                        query += " AND category = %s"
                        params.append(filters['category'])

                    if filters.get('incident_type'):
                        query += " AND incident_type = %s"
                        params.append(filters['incident_type'])

                    if filters.get('location_type'):
                        query += " AND location_type = %s"
                        params.append(filters['location_type'])

                    if filters.get('object_type'):
                        query += " AND object_type = %s"
                        params.append(filters['object_type'])

                    # Фильтрация по тегам
                    if filters.get('extracted_tags'):
                        for tag in filters['extracted_tags']:
                            if tag.strip():
                                query += " AND (tags ILIKE %s OR keywords ILIKE %s)"
                                params.extend([f'%{tag.strip()}%', f'%{tag.strip()}%'])

                    cursor.execute(query, params)
                    return [row[0] for row in cursor.fetchall()]

            return await sync_to_async(filter_sync)()

        except Exception as e:
            logger.error(f"Ошибка фильтрации услуг: {e}")
            return []


# Пример использования
if __name__ == "__main__":
    async def test_llm_filter():
        filler = LLMFilterFillerService()

        test_texts = [
            "У меня в квартире течет труба на кухне",
            "Сломался лифт, не едет на 5 этаж",
            "Нет отопления, холодно",
            "Вызовите сантехника, засорилась раковина"
        ]

        for text in test_texts:
            print(f"\nТекст: {text}")
            filters = await filler.fill_filters_from_text(text)
            print(f"Фильтры: {json.dumps(filters, ensure_ascii=False, indent=2)}")

    asyncio.run(test_llm_filter())