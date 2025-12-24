#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AIAgentService - микросервис поиска с помощью ИИ (YandexGPT)
"""

import logging
import json
import re
from typing import List, Dict, Any
from decouple import config
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class AIAgentService:
    """Микросервис поиска услуг с помощью YandexGPT"""

    # Цены YandexGPT (руб за 1000 токенов)
    PRICE_INPUT_PER_1K = 0.20
    PRICE_OUTPUT_PER_1K = 0.20

    def __init__(self):
        self.api_key = config('YANDEX_API_KEY')
        self.folder_id = config('YANDEX_FOLDER_ID')
        self.is_available = bool(self.api_key and self.folder_id)
        self.service_cache = None
        self.service_list = None

        # Статистика использования
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.requests_count = 0

        logger.info(f"AIAgentService инициализирован (доступен: {self.is_available})")

    async def _load_services(self) -> List[Dict]:
        """Асинхронная загрузка списка услуг для промпта"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT service_id, scenario_name, description_for_search
                        FROM services_catalog
                        WHERE is_active = TRUE
                        ORDER BY service_id
                    """)
                    results = cursor.fetchall()

                services = []
                for service_id, name, description in results:
                    desc = description or name
                    services.append({
                        'id': service_id,
                        'name': name,
                        'description': desc
                    })

                return services[:50]  # Ограничиваем для промпта

            self.service_cache = await sync_to_async(load_sync)()
            self.service_list = self.service_cache  # Используем тот же список
            logger.info(f"AIAgentService: загружено {len(self.service_list)} услуг для ИИ анализа")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = []
            self.service_list = []

    def _create_service_detection_prompt(self, message_text: str) -> str:
        """
        Создание промпта для определения услуги

        ПРАВИЛА ПОВЕДЕНИЯ:
        - Имитировать реальную устную речь диспетчера УК
        - Не использовать эмодзи
        - Не использовать цифры при перечислении (пишите bullet points без цифр)
        - Задавать открытые уточняющие вопросы
        """
        if not self.service_cache:
            return ""

        services_text = "\n".join([
            f"{i+1}. [ID: {s['id']}] {s['name']} - {s['description']}"
            for i, s in enumerate(self.service_cache)
        ])

        prompt = f"""
Ты - опытный диспетчер управляющей компании. Твоя задача - понять проблему человека и определить нужную услугу.

Доступные услуги:
{services_text}

Обращение человека: "{message_text}"

Проанализируй и верни JSON в формате:
{{"service_id": <ID_услуги>, "confidence": <уверенность_от_0_до_1>, "reason": "<обоснование>", "clarification": "<уточняющий_вопрос_если_нужен>"}}

Правила:
- service_id - точный ID из списка выше, или null если не уверен
- confidence - от 0.0 до 1.0, где 1.0 = полная уверенность
- reason - краткое объяснение выбора
- clarification - открытый уточняющий вопрос если confidence < 0.75, иначе пустая строка
- Если человек уже ответил на уточняющий вопрос, используй этот контекст
- При неуверенности задавай вопросы по сути: "Где именно течет?", а не "в квартире или на общедомовом имуществе?"

Верни только JSON, без другого текста.

JSON:"""

        return prompt

    async def _call_yandex_gpt(self, prompt: str) -> str:
        """
        Вызов YandexGPT API с логированием токенов и стоимости

        Returns:
            tuple(str, dict): (response_text, usage_info) или (None, None)
        """
        try:
            import aiohttp
            import asyncio

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
                    "temperature": 0.3,
                    "maxTokens": 500  # ИСПРАВЛЕНО: Увеличено для получения полных ответов
                },
                "messages": [
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    logger.info(f"AIAgent: API response status: {response.status}")

                    if response.status == 200:
                        result = await response.json()
                        logger.debug(f"AIAgent: API response JSON: {result}")

                        # Извлекаем информацию о токенах
                        usage = result.get('result', {}).get('usage', {})
                        # ИСПРАВЛЕНО: YandexGPT API возвращает токены как СТРОКИ, конвертируем в int
                        input_tokens = int(usage.get('inputTextTokens', 0) or 0)
                        output_tokens = int(usage.get('completionTokens', 0) or 0)
                        total_tokens = int(usage.get('totalTokens', input_tokens + output_tokens) or 0)

                        # Рассчитываем стоимость
                        input_cost = (input_tokens / 1000) * self.PRICE_INPUT_PER_1K
                        output_cost = (output_tokens / 1000) * self.PRICE_OUTPUT_PER_1K
                        total_cost = input_cost + output_cost

                        # Обновляем статистику
                        self.total_tokens_used += total_tokens
                        self.total_cost += total_cost
                        self.requests_count += 1

                        # Логируем с информацией о стоимости
                        logger.info(
                            f"AIAgent: API вызов завершен. "
                            f"Токены: {input_tokens} вх + {output_tokens} вых = {total_tokens} всего. "
                            f"Стоимость: {input_cost:.4f} + {output_cost:.4f} = {total_cost:.4f} руб. "
                            f"Всего потрачено: {self.total_cost:.4f} руб ({self.total_tokens_used} токенов, {self.requests_count} запросов)"
                        )

                        response_text = result['result']['alternatives'][0]['message']['text']
                        usage_info = {
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens,
                            'total_tokens': total_tokens,
                            'input_cost': input_cost,
                            'output_cost': output_cost,
                            'total_cost': total_cost
                        }

                        return response_text, usage_info
                    else:
                        error_text = await response.text()
                        logger.error(f"YandexGPT API error: {response.status} - {error_text}")
                        return None, None

        except Exception as e:
            logger.error(f"Ошибка вызова YandexGPT: {e}")
            return None, None

    def _parse_ai_response(self, response_text: str) -> Dict:
        """Парсинг ответа от ИИ"""
        try:
            if not response_text:
                return {}

            # Ищем JSON в ответе
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                # Если JSON не найден, пробуем весь ответ
                return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}, ответ: {response_text}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка обработки ответа ИИ: {e}")
            return {}

    async def search(self, message_text: str) -> Dict:
        """
        Поиск услуг с помощью ИИ

        Args:
            message_text: Текст сообщения пользователя

        Returns:
            Dict: Результат поиска в формате JSON {[КодУслуги], [Релевантность]}
                  + usage_info с информацией о токенах и стоимости
        """
        try:
            logger.info(f"AIAgent: ИИ-анализ текста '{message_text[:50]}...'")

            if not self.is_available:
                logger.warning("AIAgent: недоступен (нет API ключа)")
                return {'candidates': [], 'status': 'unavailable'}

            # Загружаем услуги если еще не загружены
            if self.service_cache is None:
                await self._load_services()

            if not self.service_cache:
                logger.warning("AIAgent: нет загруженных услуг")
                return {'candidates': [], 'status': 'no_services'}

            # Создаем промпт
            prompt = self._create_service_detection_prompt(message_text)
            logger.info(f"AIAgent: отправляем промпт в YandexGPT (длина: {len(prompt)} символов)")
            logger.debug(f"AIAgent: промпт: {prompt[:500]}...")  # Первые 500 символов

            # Вызываем ИИ (уже в async контексте)
            response, usage_info = await self._call_yandex_gpt(prompt)

            if not response:
                logger.warning("AIAgent: не получили ответ от ИИ")
                return {'candidates': [], 'status': 'no_response', 'usage_info': None}

            # Парсим ответ
            parsed = self._parse_ai_response(response)

            if not parsed:
                logger.warning(f"AIAgent: не удалось распарсить ответ: {response}")
                return {'candidates': [], 'status': 'parse_error', 'usage_info': usage_info}

            service_id = parsed.get('service_id')
            confidence = parsed.get('confidence', 0.0)

            # Проверяем порог уверенности
            if confidence >= 0.75 and service_id:
                # Ищем информацию об услуге
                service_info = next((s for s in self.service_list if s['id'] == service_id), None)

                if service_info:
                    candidate = {
                        'service_id': service_id,
                        'service_name': service_info['name'],
                        'confidence': round(confidence, 3),
                        'source': 'ai_agent',
                        'reason': parsed.get('reason', '')
                    }

                    logger.info(f"AIAgent: найдена услуга {service_id} с уверенностью {confidence:.3f}")

                    return {
                        'status': 'success',
                        'candidates': [candidate],
                        'ai_response': response,
                        'parsed_result': parsed,
                        'usage_info': usage_info,
                        'method': 'ai_search'
                    }

            # Если не достигли порога или не нашли услугу
            logger.info(f"AIAgent: не найдено подходящих услуг (confidence: {confidence})")
            return {
                'status': 'low_confidence',
                'candidates': [],
                'ai_response': response,
                'parsed_result': parsed,
                'usage_info': usage_info
            }

        except Exception as e:
            logger.error(f"Ошибка в AIAgentService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }

    def get_service_details(self, service_id: int) -> Dict:
        """Получить детали услуги по ID"""
        service = next((s for s in self.service_list if s['id'] == service_id), None)
        return service or {}