#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UnifiedLLMService - централизованный сервис для всех LLM запросов
Единая точка для вызовов YandexGPT с логированием, учетом токенов и выбором модели
"""

import logging
import json
import asyncio
import time
import os
import aiohttp
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class UnifiedLLMService:
    """Централизованный сервис для работы с LLM моделями"""

    def __init__(self):
        # API настройки
        self.providers = {
            'yandex': {
                'api_key': os.getenv("YANDEX_API_KEY", ""),
                'folder_id': os.getenv("YANDEX_FOLDER_ID", ""),
                'base_url': "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
                'models': {
                    'yandexgpt-lite': {
                        'uri_template': "gpt://{folder_id}/yandexgpt-lite/latest",
                        'cost_per_1k_tokens': 0.00024,  # ₽ за 1000 токенов
                        'max_tokens': 8000,
                        'default_temperature': 0.2
                    },
                    'yandexgpt-pro': {
                        'uri_template': "gpt://{folder_id}/yandexgpt-pro/latest",
                        'cost_per_1k_tokens': 0.0005,
                        'max_tokens': 8000,
                        'default_temperature': 0.3
                    }
                }
            }
        }

        self.default_provider = 'yandex'
        self.default_model = 'yandexgpt-lite'
        logger.info("UnifiedLLMService инициализирован")

    async def make_request(
        self,
        prompt: str,
        service_type: str = "general",
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        user_id: Optional[int] = None,
        dialog_id: Optional[str] = None,
        additional_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Единый метод для выполнения LLM запроса

        Args:
            prompt: Основной промпт
            service_type: Тип сервиса (service_detection, address_extraction, filter_filling, etc.)
            model: Модель (если не указана - используется default)
            provider: Провайдер (если не указан - используется default)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
            system_prompt: Системный промпт
            user_id: ID пользователя
            dialog_id: ID диалога
            additional_data: Дополнительные данные

        Returns:
            Dict: Результат запроса
        """
        # Определяем модель и провайдера
        provider = provider or self.default_provider
        model = model or self.default_model

        if provider not in self.providers:
            raise ValueError(f"Провайдер {provider} не поддерживается")

        if model not in self.providers[provider]['models']:
            raise ValueError(f"Модель {model} не поддерживается провайдером {provider}")

        # Замер времени начала
        start_time = time.time()

        try:
            logger.info(f"LLM запрос: {service_type} | модель: {model} | пользователь: {user_id}")

            # Формируем запрос
            request_data = self._build_request_data(
                prompt=prompt,
                model=model,
                provider=provider,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt
            )

            # Выполняем запрос
            response_text, input_tokens, output_tokens = await self._execute_request(
                provider=provider,
                request_data=request_data
            )

            # Считаем время выполнения
            response_time_ms = int((time.time() - start_time) * 1000)

            # Рассчитываем стоимость
            total_tokens = input_tokens + output_tokens
            cost_rub = self._calculate_cost(provider, model, total_tokens)

            # Логируем запрос
            await self._log_request(
                user_id=user_id,
                dialog_id=dialog_id,
                service_type=service_type,
                provider=provider,
                model=model,
                prompt_text=prompt,
                response_text=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_rub=cost_rub,
                response_time_ms=response_time_ms,
                success=True,
                additional_data=additional_data
            )

            # Возвращаем результат
            result = {
                'success': True,
                'response_text': response_text,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_rub': cost_rub,
                'response_time_ms': response_time_ms,
                'model_used': model,
                'provider_used': provider
            }

            logger.info(f"LLM успешный ответ: {total_tokens} токенов, {cost_rub:.4f}₽, {response_time_ms}мс")
            return result

        except Exception as e:
            # Логируем ошибку
            response_time_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)

            await self._log_request(
                user_id=user_id,
                dialog_id=dialog_id,
                service_type=service_type,
                provider=provider,
                model=model,
                prompt_text=prompt,
                response_text=None,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                cost_rub=0.0,
                response_time_ms=response_time_ms,
                success=False,
                error_message=error_message,
                additional_data=additional_data
            )

            logger.error(f"LLM ошибка: {service_type} | {error_message}")

            result = {
                'success': False,
                'error': error_message,
                'response_text': None,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'cost_rub': 0.0,
                'response_time_ms': response_time_ms,
                'model_used': model,
                'provider_used': provider
            }

            return result

    def _build_request_data(
        self,
        prompt: str,
        model: str,
        provider: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        system_prompt: Optional[str]
    ) -> Dict:
        """Формирование данных запроса к API"""

        model_config = self.providers[provider]['models'][model]

        messages = []
        if system_prompt:
            messages.append({
                "role": "system",
                "text": system_prompt
            })

        messages.append({
            "role": "user",
            "text": prompt
        })

        return {
            "modelUri": model_config['uri_template'].format(folder_id=self.providers[provider]['folder_id']),
            "completionOptions": {
                "stream": False,
                "temperature": temperature or model_config['default_temperature'],
                "maxTokens": max_tokens or 1000
            },
            "messages": messages
        }

    async def _execute_request(self, provider: str, request_data: Dict) -> tuple[str, int, int]:
        """Выполнение HTTP запроса к API"""

        if provider == 'yandex':
            return await self._execute_yandex_request(request_data)
        else:
            raise ValueError(f"Провайдер {provider} не реализован")

    async def _execute_yandex_request(self, request_data: Dict) -> tuple[str, int, int]:
        """Выполнение запроса к YandexGPT API"""

        headers = {
            "Authorization": f"Bearer {self.providers['yandex']['api_key']}",
            "x-folder-id": self.providers['yandex']['folder_id'],
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.providers['yandex']['base_url'],
                headers=headers,
                json=request_data
            ) as response:

                if response.status == 200:
                    result = await response.json()

                    response_text = result['result']['alternatives'][0]['message']['text']
                    usage = result['result']['usage']

                    input_tokens = usage.get('inputTextTokens', 0)
                    output_tokens = usage.get('completionTokens', 0)

                    return response_text, input_tokens, output_tokens
                else:
                    error_text = await response.text()
                    raise Exception(f"YandexGPT API error: {response.status} - {error_text}")

    def _calculate_cost(self, provider: str, model: str, total_tokens: int) -> float:
        """Расчет стоимости запроса"""
        model_config = self.providers[provider]['models'][model]
        cost_per_token = model_config['cost_per_1k_tokens'] / 1000
        return total_tokens * cost_per_token

    async def _log_request(
        self,
        user_id: Optional[int],
        dialog_id: Optional[str],
        service_type: str,
        provider: str,
        model: str,
        prompt_text: str,
        response_text: Optional[str],
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost_rub: float,
        response_time_ms: int,
        success: bool,
        error_message: Optional[str] = None,
        additional_data: Optional[Dict] = None
    ):
        """Логирование запроса в БД"""
        try:
            def log_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO ai_cost_tracking (
                            dialog_id,
                            user_id,
                            ai_provider,
                            model_name,
                            service_type,
                            input_tokens,
                            output_tokens,
                            total_tokens,
                            cost_rub,
                            request_timestamp,
                            response_time_ms,
                            success,
                            error_message,
                            additional_data
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s
                        )
                    """, [
                        dialog_id,
                        user_id,
                        provider,
                        model,
                        service_type,
                        input_tokens,
                        output_tokens,
                        total_tokens,
                        cost_rub,
                        response_time_ms,
                        success,
                        error_message,
                        json.dumps(additional_data) if additional_data else None
                    ])

            await sync_to_async(log_sync)()

        except Exception as e:
            logger.error(f"Ошибка логирования LLM запроса: {e}")

    # Удобные методы для разных типов запросов

    async def detect_service(
        self,
        message_text: str,
        user_id: Optional[int] = None,
        dialog_id: Optional[str] = None
    ) -> Dict:
        """Определение услуги по тексту"""

        prompt = f"""
Проанализируй обращение пользователя и определи наиболее подходящую услугу.

Текст обращения: "{message_text}"

Верни JSON с информацией:
{{
    "detected_service": "название услуги или ''",
    "service_id": "ID услуги или null",
    "confidence": 0.95,
    "category": "категория услуги",
    "urgency": "low/medium/high/critical",
    "needs_clarification": true,
    "clarification_question": "Уточняющий вопрос если нужно"
}}
"""

        return await self.make_request(
            prompt=prompt,
            service_type="service_detection",
            system_prompt="Ты - эксперт по ЖКУ услугам. Определяй услуги по тексту обращений.",
            user_id=user_id,
            dialog_id=dialog_id
        )

    async def extract_address(
        self,
        message_text: str,
        user_id: Optional[int] = None,
        dialog_id: Optional[str] = None
    ) -> Dict:
        """Извлечение адреса из текста"""

        prompt = f"""
Извлеки адрес из текста сообщения.

Текст: "{message_text}"

Верни JSON:
{{
    "street": "улица или ''",
    "house_number": "номер дома или ''",
    "apartment_number": "номер квартиры или ''",
    "confidence": 0.95,
    "is_complete": true,
    "needs_clarification": false,
    "clarification_type": "street/house/apartment"
}}
"""

        return await self.make_request(
            prompt=prompt,
            service_type="address_extraction",
            system_prompt="Ты - эксперт по извлечению адресов из текста.",
            user_id=user_id,
            dialog_id=dialog_id
        )

    async def fill_filters(
        self,
        message_text: str,
        dialog_context: str = "",
        user_id: Optional[int] = None,
        dialog_id: Optional[str] = None
    ) -> Dict:
        """Заполнение фильтров услуг"""

        prompt = f"""
Заполни фильтры для поиска услуг.

Текст: "{message_text}"
Контекст: "{dialog_context}"

Верни JSON:
{{
    "category": "категория или ''",
    "incident_type": "тип инцидента или ''",
    "location_type": "тип локации или ''",
    "urgency_level": "low/medium/high/critical",
    "confidence_scores": {{}},
    "extracted_tags": [],
    "reasoning": "объяснение"
}}
"""

        return await self.make_request(
            prompt=prompt,
            service_type="filter_filling",
            system_prompt="Ты - аналитик ЖКУ услуг. Заполняй фильтры на основе текста.",
            user_id=user_id,
            dialog_id=dialog_id
        )

    async def get_daily_stats(self, date: Optional[datetime] = None) -> Dict:
        """Получение суточной статистики использования"""

        target_date = date or datetime.now().date()

        try:
            def stats_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT
                            COUNT(*) as requests_count,
                            SUM(total_tokens) as total_tokens,
                            SUM(cost_rub) as total_cost_rub,
                            AVG(response_time_ms) as avg_response_time,
                            SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful_requests
                        FROM ai_cost_tracking
                        WHERE DATE(request_timestamp) = %s
                    """, [target_date])

                    return cursor.fetchone()

            result = await sync_to_async(stats_sync)()

            if result:
                requests_count, total_tokens, total_cost_rub, avg_response_time, successful_requests = result

                return {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'requests_count': requests_count or 0,
                    'total_tokens': total_tokens or 0,
                    'total_cost_rub': float(total_cost_rub or 0),
                    'avg_response_time_ms': float(avg_response_time or 0),
                    'success_rate': (successful_requests / requests_count * 100) if requests_count > 0 else 0
                }
            else:
                return {
                    'date': target_date.strftime('%Y-%m-%d'),
                    'requests_count': 0,
                    'total_tokens': 0,
                    'total_cost_rub': 0.0,
                    'avg_response_time_ms': 0.0,
                    'success_rate': 0.0
                }

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {'error': str(e)}


# Глобальный экземпляр сервиса
unified_llm_service = UnifiedLLMService()