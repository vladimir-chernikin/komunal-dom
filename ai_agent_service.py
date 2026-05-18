#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AIAgentService - ЕДИНЫЙ микросервис для всех LLM запросов

Поддерживаемые провайдеры:
- YandexGPT (Lite, Pro)
- GigaChat (GigaChat, GigaChat-2, GigaChat-Plus, GigaChat-2.1)

Правила использования (КРИТИЧЕСКИ ВАЖНО):
- ВСЕ LLM запросы ДОЛЖНЫ проходить через AIAgentService
- ЗАПРЕЩЕНО прямые HTTP запросы к API из других сервисов
- Единая точка входа для подсчета стоимости и логирования

Дата создания: 2025-12-25
Последнее обновление: 2025-12-28
"""

import logging
import json
import re
import uuid
import time  # ИСПРАВЛЕНО (2026-03-05): Для замера времени LLM вызовов
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from decouple import config
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class AIAgentService:
    """
    Единый микросервис для всех LLM запросов (YandexGPT + GigaChat)

    Использование:
        service = AIAgentService()
        response, usage = await service.call_llm(
            prompt="...",
            provider="yandexgpt",  # yandexgpt | gigachat
            model="lite"           # lite/pro | GigaChat/GigaChat-2/GigaChat-Plus/GigaChat-2.1
        )
    """

    # Цены YandexGPT (руб за 1000 токенов)
    YANDEX_PRICES = {
        'lite': {'input': 0.20, 'output': 0.20},
        'pro': {'input': 3.00, 'output': 3.00}
    }

    # Цены GigaChat (руб за 1000 токенов)
    # Текущий API scope не отдает GigaChat-2-Lite; используем доступные модели из /api/v1/models
    GIGACHAT_PRICES = {
        'GigaChat': 0.50,
        'GigaChat-2': 1.50,  # Синхронный режим
        'GigaChat-Plus': 3.00,
        'GigaChat-2.1': 1.80
    }

    # Цены Yandex Embeddings (руб за 1000 токенов) - ПРЕДВАРИТЕЛЬНО
    YANDEX_EMBEDDING_PRICES = {
        'text-search-doc': 0.10  # Приблизительно (обычно дешевле LLM)
    }

    # Class variables for connection pooling (ОПТИМИЗАЦИЯ 2026-03-05)
    _yandex_session = None
    _gigachat_client = None
    _gigachat_token_cache = {}
    _gigachat_token_lock = None

    def __init__(
        self,
        provider: str = None,
        default_model: Optional[str] = None,
        tracer=None,
        gigachat_profile: Optional[str] = None,
    ):
        """
        Инициализация сервиса

        Args:
            provider: Провайдер по умолчанию (yandexgpt | gigachat), если None - из env (DEFAULT_LLM_PROVIDER)
            default_model: Модель по умолчанию (если None, используется из конфига)
            tracer: PerformanceTracer для трекинга производительности
            gigachat_profile: профиль GigaChat-конфига: default | alt
        """
        # ИСПРАВЛЕНО (2026-03-10): Читаем провайдера из env если не указан
        if provider is None:
            provider = config('DEFAULT_LLM_PROVIDER', default='gigachat')

        # Параметры YandexGPT
        self.yandexgpt_api_key = config('YANDEX_API_KEY', default=None)
        self.yandexgpt_folder_id = config('YANDEX_FOLDER_ID', default=None)
        self.yandexgpt_default_model = config('YANDEXGPT_MODEL', default='lite')

        # Параметры GigaChat
        self.gigachat_profile = (gigachat_profile or config('GIGACHAT_PROFILE', default='default')).strip().lower()
        self.gigachat_client_id = self._gigachat_config('CLIENT_ID', default='019b65dd-feb9-756f-a83e-330d88d76fa0')
        self.gigachat_auth_key = self._gigachat_config('AUTH_KEY', default='MDE5YjY1ZGQtZmViOS03NTZmLWE4M2UtMzMwZDg4ZDc2ZmEwOjYyODNjZGRiLTBiNGYtNDZhMS04NDVlLWZjOTYyYWE2ZWFiYg==')
        self.gigachat_scope = self._gigachat_config('SCOPE', default='GIGACHAT_API_PERS')
        self.gigachat_default_model = self._gigachat_config('MODEL', default='GigaChat-2')

        # Текущий провайдер и модель
        self.provider = provider
        self.default_model = default_model or self._get_default_model()

        # ИСПРАВЛЕНО (2026-03-05): Performance tracer
        self.tracer = tracer

        # Проверка доступности
        self.yandexgpt_available = bool(self.yandexgpt_api_key and self.yandexgpt_folder_id)
        self.gigachat_available = bool(self.gigachat_client_id and self.gigachat_auth_key)

        # Кеширование услуг
        self.service_cache = None
        self.service_list = None

        # Статистика использования (в памяти)
        self.stats = {
            'total_requests': 0,
            'total_tokens': 0,
            'total_cost': 0.0,
            'yandexgpt': {'requests': 0, 'tokens': 0, 'cost': 0.0},
            'gigachat': {'requests': 0, 'tokens': 0, 'cost': 0.0},
            'embeddings': {'requests': 0, 'tokens': 0, 'cost': 0.0}  # ИСПРАВЛЕНО (2026-01-13): Отдельная статистика для embeddings
        }

        # OAuth токен GigaChat
        self._gigachat_token = None
        self._gigachat_token_expires = None

        logger.info(
            f"AIAgentService инициализирован: "
            f"provider={provider}, model={self.default_model}, gigachat_profile={self.gigachat_profile}, "
            f"yandexgpt={self.yandexgpt_available}, gigachat={self.gigachat_available}, "
            f"embeddings=True (Yandex), connection_pool=True"
        )

    def _gigachat_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self.gigachat_profile and self.gigachat_profile not in {'default', 'prod', 'primary'}:
            profiled_key = f"GIGACHAT_{self.gigachat_profile.upper()}_{key}"
            value = config(profiled_key, default=None)
            if value not in (None, ''):
                return value
        return config(f"GIGACHAT_{key}", default=default)

    def _get_default_model(self) -> str:
        """Получить модель по умолчанию для текущего провайдера"""
        if self.provider == 'gigachat':
            return self.gigachat_default_model
        else:
            return self.yandexgpt_default_model

    @classmethod
    async def _get_yandex_session(cls):
        """
        Получить или создать aiohttp сессию для Yandex API (ОПТИМИЗАЦИЯ 2026-03-05)

        Connection Pool с Keep-Alive для переиспользования TCP соединений
        """
        if cls._yandex_session is None or cls._yandex_session.closed:
            import aiohttp
            # Создаем сессию с connection pooling
            connector = aiohttp.TCPConnector(
                limit=100,  # Максимальное количество соединений
                limit_per_host=20,  # Максимальное соединений на хост
                ttl_dns_cache=300,  # Кеширование DNS 5 минут
                keepalive_timeout=60,  # Keep-Alive 60 секунд
                enable_cleanup_closed=True  # Очистка закрытых соединений
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            cls._yandex_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                raise_for_status=False
            )
            logger.info("AIAgentService: создана новая aiohttp сессия с connection pooling")
        return cls._yandex_session

    @classmethod
    async def _get_gigachat_client(cls):
        """
        Получить или создать httpx клиент для GigaChat (ОПТИМИЗАЦИЯ 2026-03-05)

        Connection Pool с Keep-Alive для переиспользования TCP соединений
        """
        if cls._gigachat_client is None:
            import httpx
            # Создаем клиент с connection pooling
            limits = httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=60
            )
            cls._gigachat_client = httpx.AsyncClient(
                verify=False,
                timeout=30.0,
                limits=limits
            )
            logger.info("AIAgentService: создан новый httpx клиент с connection pooling")
        return cls._gigachat_client

    @classmethod
    async def close_connections(cls):
        """
        Закрыть все connection pools (ОПТИМИЗАЦИЯ 2026-03-05)

        Вызывать при graceful shutdown
        """
        if cls._yandex_session and not cls._yandex_session.closed:
            await cls._yandex_session.close()
            logger.info("AIAgentService: aiohttp сессия закрыта")
        if cls._gigachat_client:
            await cls._gigachat_client.aclose()
            logger.info("AIAgentService: httpx клиент закрыт")

    async def _load_services(self) -> List[Dict]:
        """Асинхронная загрузка списка услуг для промпта"""
        if self.service_cache:
            return self.service_cache

        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-03-25): Новая структура - поле description вместо description_for_search
                    cursor.execute("""
                        SELECT service_id, scenario_name, description
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
            self.service_list = self.service_cache
            logger.info(f"AIAgentService: загружено {len(self.service_list)} услуг для ИИ анализа")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = []
            self.service_list = []

        return self.service_cache

    async def call_llm(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        session_id: Optional[str] = None,
        message_id: Optional[int] = None,
        caller_service: Optional[str] = None,
        prompt_slug: Optional[str] = None,
        prompt_source: str = 'runtime_generated',
        service_name: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        ЕДИНЫЙ МЕТОД ДЛЯ ВСЕХ LLM ЗАПРОСОВ

        ИСПРАВЛЕНО (2026-01-06):
        - Добавлен параметр session_id для связи с dialog_logs
        - Добавлен параметр message_id для надежной связи с сообщением
        ИСПРАВЛЕНО (2026-02-24):
        - Добавлен параметр service_name для отслеживания микросервиса

        Args:
            prompt: Промпт для LLM
            provider: Провайдер (yandexgpt | gigachat), если None - используется из __init__
            model: Модель, если None - используется default_model
            temperature: Температура (0.0 - 1.0)
            max_tokens: Максимальное количество токенов
            session_id: ID сессии диалога (для сохранения в llm_request_log)
            message_id: ID сообщения из dialog_logs (для надежной связи)
            service_name: Имя микросервиса (FilterDetectionService, MainAgent, и т.д.)

        Returns:
            (response_text, usage_info)

        Raises:
            ValueError: Неверный провайдер или модель
            Exception: Ошибка API

        Пример:
            response, usage = await service.call_llm(
                "Привет! Как дела?",
                provider="gigachat",
                model="GigaChat"
            )
            print(usage['cost_rub'])  # 0.05
        """
        # Определяем провайдер и модель
        provider = provider or self.provider
        model = model or self.default_model
        caller_service = caller_service or service_name

        # Вызываем соответствующий провайдер
        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id в методы
        # ИСПРАВЛЕНО (2026-02-24): Передаем service_name в методы
        if provider == 'yandexgpt':
            return await self._call_yandexgpt(
                prompt, model, temperature, max_tokens, session_id, message_id,
                caller_service, prompt_slug, prompt_source
            )
        elif provider == 'gigachat':
            return await self._call_gigachat(
                prompt, model, temperature, max_tokens, session_id, message_id,
                caller_service, prompt_slug, prompt_source
            )
        else:
            raise ValueError(f"Неверный провайдер: {provider}. Доступно: yandexgpt, gigachat")

    async def _call_yandexgpt(
        self,
        prompt: str,
        model: str = 'lite',
        temperature: float = 0.7,
        max_tokens: int = 1000,
        session_id: Optional[str] = None,
        message_id: Optional[int] = None,
        caller_service: Optional[str] = None,
        prompt_slug: Optional[str] = None,
        prompt_source: str = 'runtime_generated'
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Вызов YandexGPT API

        ИСПРАВЛЕНО (2026-01-06):
        - Добавлен параметр session_id для связи с dialog_logs
        - Добавлен параметр message_id для надежной связи с сообщением
        ИСПРАВЛЕНО (2026-02-24):
        - Добавлен параметр service_name для отслеживания микросервиса
        """

        if not self.yandexgpt_available:
            raise Exception("YandexGPT недоступен (не настроен API key или folder ID)")

        # Проверяем валидность модели
        if model not in ['lite', 'pro']:
            logger.warning(f"Неверная модель YandexGPT '{model}', используем 'lite'")
            model = 'lite'

        # Определяем modelUri и цены
        if model == 'pro':
            model_uri = f"gpt://{self.yandexgpt_folder_id}/yandexgpt/latest"
            price_input = self.YANDEX_PRICES['pro']['input']
            price_output = self.YANDEX_PRICES['pro']['output']
        else:  # lite
            model_uri = f"gpt://{self.yandexgpt_folder_id}/yandexgpt-lite/latest"
            price_input = self.YANDEX_PRICES['lite']['input']
            price_output = self.YANDEX_PRICES['lite']['output']

        try:
            import aiohttp
            import asyncio

            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

            headers = {
                "Authorization": f"Bearer {self.yandexgpt_api_key}",
                "x-folder-id": self.yandexgpt_folder_id,
                "Content-Type": "application/json"
            }

            data = {
                "modelUri": model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": temperature,
                    "maxTokens": max_tokens
                },
                "messages": [
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }

            # Логирование промпта
            logger.debug(f"AIAgentService: YandexGPT PROMPT:\n{prompt}")

            # ИСПРАВЛЕНО (2026-03-05): Замер времени LLM вызова
            llm_start = time.perf_counter()

            # ОПТИМИЗАЦИЯ (2026-03-05): Используем connection pool вместо новой сессии
            session = await self._get_yandex_session()
            async with session.post(
                url,
                headers=headers,
                json=data
            ) as response:
                logger.info(f"AIAgentService: YandexGPT API response: {response.status} (model: {model})")

                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"AIAgentService: YandexGPT RESPONSE JSON: {result}")

                    # Извлекаем ответ
                    alternatives = result.get('result', {}).get('alternatives', [])
                    if not alternatives:
                        raise Exception("Пустой ответ от YandexGPT")

                    response_text = alternatives[0]['message']['text']

                    # Извлекаем информацию о токенах
                    usage = result.get('result', {}).get('usage', {})
                    input_tokens = int(usage.get('inputTextTokens', 0) or 0)
                    output_tokens = int(usage.get('completionTokens', 0) or 0)
                    total_tokens = int(usage.get('totalTokens', input_tokens + output_tokens) or 0)

                    # Рассчитываем стоимость
                    input_cost = (input_tokens / 1000) * price_input
                    output_cost = (output_tokens / 1000) * price_output
                    total_cost = input_cost + output_cost

                    # ИСПРАВЛЕНО (2026-03-05): Вычисляем время выполнения
                    duration_ms = (time.perf_counter() - llm_start) * 1000

                    # ИСПРАВЛЕНО (2026-03-05): Регистрируем LLM вызов в PerformanceTracer
                    if self.tracer:
                        self.tracer.track_llm_call(
                            provider='yandexgpt',
                            model=model,
                            prompt_tokens=input_tokens,
                            completion_tokens=output_tokens,
                            cost_rub=total_cost,
                            service_name=caller_service or 'AIAgentService',
                            duration_ms=duration_ms,
                            prompt_length=len(prompt),
                            response_length=len(response_text),
                            prompt=prompt[:500],  # ИСПРАВЛЕНО (2026-03-05): Сохраняем первые 500 символов
                            response=response_text[:500]  # ИСПРАВЛЕНО (2026-03-05): Сохраняем первые 500 символов
                        )

                    # Формируем usage_info
                    usage_info = {
                        'provider': 'yandexgpt',
                        'model': model,
                        'prompt_tokens': input_tokens,
                        'completion_tokens': output_tokens,
                        'total_tokens': total_tokens,
                        'cost_rub': round(total_cost, 4),
                        'input_cost': round(input_cost, 4),
                        'output_cost': round(output_cost, 4)
                    }

                    # Логирование ответа
                    logger.debug(f"AIAgentService: YandexGPT RESPONSE:\n{response_text}")
                    logger.info(
                        f"AIAgentService: YandexGPT завершен. "
                        f"Токенов: {total_tokens} (in: {input_tokens}, out: {output_tokens}), "
                        f"стоимость: {total_cost:.4f} руб."
                    )

                    # Обновляем статистику
                    self._update_statistics('yandexgpt', total_tokens, total_cost)

                    # Сохраняем в БД
                    # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для связи с dialog_logs
                    # ИСПРАВЛЕНО (2026-02-24): Передаем service_name для отслеживания микросервиса
                    await self._save_statistics_to_db(
                        provider='yandexgpt',
                        model=model,
                        prompt=prompt,
                        response=response_text,
                        usage_info=usage_info,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        prompt_source=prompt_source
                    )

                    return response_text, usage_info
                else:
                    error_text = await response.text()
                    raise Exception(f"YandexGPT API error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Ошибка при вызове YandexGPT: {e}")
            raise

    async def _call_gigachat(
        self,
        prompt: str,
        model: str = 'GigaChat',
        temperature: float = 0.7,
        max_tokens: int = 1000,
        session_id: Optional[str] = None,
        message_id: Optional[int] = None,
        caller_service: Optional[str] = None,
        prompt_slug: Optional[str] = None,
        prompt_source: str = 'runtime_generated'
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Вызов GigaChat API

        ИСПРАВЛЕНО (2026-01-06):
        - Добавлен параметр session_id для связи с dialog_logs
        - Добавлен параметр message_id для надежной связи с сообщением
        ИСПРАВЛЕНО (2026-02-24):
        - Добавлен параметр service_name для отслеживания микросервиса
        """
        if not self.gigachat_available:
            raise Exception("GigaChat недоступен (не настроен Client ID или Auth Key)")

        # Проверяем валидность модели
        if model not in self.GIGACHAT_PRICES:
            logger.warning(f"Неверная модель GigaChat '{model}', используем 'GigaChat'")
            model = 'GigaChat'

        try:
            import httpx

            # Получаем OAuth токен
            access_token = await self._get_gigachat_token()

            # Формируем запрос
            url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            # Логирование промпта
            logger.debug(f"AIAgentService: GigaChat PROMPT:\n{prompt}")

            # ИСПРАВЛЕНО (2026-03-10): Замер времени LLM вызова
            llm_start = time.perf_counter()

            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                logger.info(f"AIAgentService: GigaChat API response: {response.status_code} (model: {model})")

                if response.status_code == 200:
                    result = response.json()
                    logger.debug(f"AIAgentService: GigaChat RESPONSE JSON: {result}")

                    # Извлекаем ответ
                    response_text = result["choices"][0]["message"]["content"]

                    # Извлекаем информацию о токенах
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)

                    # Рассчитываем стоимость
                    cost_per_1k = self.GIGACHAT_PRICES[model]
                    total_cost = (total_tokens / 1000) * cost_per_1k

                    # ИСПРАВЛЕНО (2026-03-10): Вычисляем время выполнения
                    duration_ms = (time.perf_counter() - llm_start) * 1000

                    # ИСПРАВЛЕНО (2026-03-10): Регистрируем LLM вызов в PerformanceTracer
                    if self.tracer:
                        self.tracer.track_llm_call(
                            provider='gigachat',
                            model=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            cost_rub=total_cost,
                            service_name=caller_service or 'AIAgentService',
                            duration_ms=duration_ms,
                            prompt_length=len(prompt),
                            response_length=len(response_text),
                            prompt=prompt[:500],  # ИСПРАВЛЕНО (2026-03-10): Сохраняем первые 500 символов
                            response=response_text[:500]  # ИСПРАВЛЕНО (2026-03-10): Сохраняем первые 500 символов
                        )

                    # Формируем usage_info
                    usage_info = {
                        'provider': 'gigachat',
                        'model': model,
                        'prompt_tokens': prompt_tokens,
                        'completion_tokens': completion_tokens,
                        'total_tokens': total_tokens,
                        'cost_rub': round(total_cost, 4),
                        'cost_per_1k_tokens': cost_per_1k
                    }

                    # Логирование ответа
                    logger.debug(f"AIAgentService: GigaChat RESPONSE:\n{response_text}")
                    logger.info(
                        f"AIAgentService: GigaChat завершен. "
                        f"Токенов: {total_tokens} (in: {prompt_tokens}, out: {completion_tokens}), "
                        f"стоимость: {total_cost:.4f} руб."
                    )

                    # Обновляем статистику
                    self._update_statistics('gigachat', total_tokens, total_cost)

                    # Сохраняем в БД
                    # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для связи с dialog_logs
                    # ИСПРАВЛЕНО (2026-02-24): Передаем service_name для отслеживания микросервиса
                    await self._save_statistics_to_db(
                        provider='gigachat',
                        model=model,
                        prompt=prompt,
                        response=response_text,
                        usage_info=usage_info,
                        session_id=session_id,
                        message_id=message_id,
                        caller_service=caller_service,
                        prompt_slug=prompt_slug,
                        prompt_source=prompt_source
                    )

                    return response_text, usage_info
                else:
                    raise Exception(f"GigaChat API error {response.status_code}: {response.text}")

        except Exception as e:
            logger.error(f"Ошибка при вызове GigaChat: {e}")
            raise

    async def _get_gigachat_token(self) -> str:
        """Получить OAuth токен GigaChat с кешированием"""
        import httpx
        from datetime import datetime, timedelta, timezone

        # Проверяем, есть ли валидный токен
        if self._gigachat_token and self._gigachat_token_expires:
            if datetime.now(timezone.utc) < self._gigachat_token_expires:
                logger.debug("Используем кешированный токен GigaChat")
                return self._gigachat_token

        cache_key = (self.gigachat_profile, self.gigachat_auth_key, self.gigachat_scope)
        cached = self.__class__._gigachat_token_cache.get(cache_key)
        now = datetime.now(timezone.utc)
        if cached and now < cached["expires_at"]:
            self._gigachat_token = cached["token"]
            self._gigachat_token_expires = cached["expires_at"]
            logger.debug("Используем общий кешированный токен GigaChat")
            return self._gigachat_token

        if self.__class__._gigachat_token_lock is None:
            self.__class__._gigachat_token_lock = asyncio.Lock()

        async with self.__class__._gigachat_token_lock:
            cached = self.__class__._gigachat_token_cache.get(cache_key)
            now = datetime.now(timezone.utc)
            if cached and now < cached["expires_at"]:
                self._gigachat_token = cached["token"]
                self._gigachat_token_expires = cached["expires_at"]
                logger.debug("Используем общий кешированный токен GigaChat после ожидания lock")
                return self._gigachat_token

            # Генерируем уникальный RqUID
            rq_uid = str(uuid.uuid4())

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rq_uid,
                "Authorization": f"Basic {self.gigachat_auth_key}"
            }

            data = {
                "scope": self.gigachat_scope
            }

            try:
                logger.info(f"Запрос OAuth токена GigaChat (RqUID: {rq_uid})")

                async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                    response = await client.post(
                        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                        headers=headers,
                        data=data
                    )
                    response.raise_for_status()
                    token_data = response.json()

                    self._gigachat_token = token_data["access_token"]

                    # GigaChat возвращает expires_at в миллисекундах (Unix timestamp)
                    expires_at_ms = token_data.get("expires_at", 0)
                    if expires_at_ms > 0:
                        self._gigachat_token_expires = datetime.fromtimestamp(
                            expires_at_ms / 1000,
                            tz=timezone.utc
                        ) - timedelta(minutes=1)
                    else:
                        self._gigachat_token_expires = datetime.now(timezone.utc) + timedelta(minutes=29)

                    self.__class__._gigachat_token_cache[cache_key] = {
                        "token": self._gigachat_token,
                        "expires_at": self._gigachat_token_expires,
                    }

                    logger.info(
                        f"OAuth токен GigaChat получен. "
                        f"Истекает: {self._gigachat_token_expires.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )

                    return self._gigachat_token

            except Exception as e:
                logger.error(f"Ошибка при получении токена GigaChat: {e}")
                raise

    def _update_statistics(self, provider: str, tokens: int, cost: float):
        """Обновить статистику в памяти"""
        self.stats['total_requests'] += 1
        self.stats['total_tokens'] += tokens
        self.stats['total_cost'] += cost
        self.stats[provider]['requests'] += 1
        self.stats[provider]['tokens'] += tokens
        self.stats[provider]['cost'] += cost

    async def _save_statistics_to_db(
        self,
        provider: str,
        model: str,
        prompt: str,
        response: str,
        usage_info: Dict[str, Any],
        session_id: Optional[str] = None,
        message_id: Optional[int] = None,
        caller_service: Optional[str] = None,
        prompt_slug: Optional[str] = None,
        prompt_source: str = 'runtime_generated'
    ):
        """
        Сохранить статистику запроса в БД

        ИСПРАВЛЕНО (2026-01-06):
        - Добавлен параметр session_id для связи с dialog_logs
        - Добавлен параметр message_id для надежной связи с сообщением
        ИСПРАВЛЕНО (2026-02-16): Добавлены отладочные логи для response_text
        ИСПРАВЛЕНО (2026-02-24): Добавлен параметр service_name для отслеживания микросервиса
        """
        # ИСПРАВЛЕНО (2026-02-16): Отладочные логи для проверки response
        response_len = len(response) if response else 0
        response_preview = response[:100] if response else "(empty)"
        logger.info(f"[LLM-STAT] ВХОД: provider={provider}, model={model}, response_len={response_len}")
        logger.info(f"[LLM-STAT] response_preview={response_preview}")

        try:
            def save_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО (2026-02-16): Обрезаем response с проверкой
                    response_to_save = response[:5000] if response else ""

                    # ИСПРАВЛЕНО (2026-02-16): Логируем что записываем
                    logger.info(f"[LLM-STAT] ЗАПИСЬ: response_to_save_len={len(response_to_save)}")

                    cursor.execute("""
                        INSERT INTO llm_request_log (
                            request_id,
                            provider,
                            model,
                            prompt_text,
                            response_text,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                            cost_rub,
                            session_id,
                            message_id,
                            caller_service,
                            prompt_slug,
                            prompt_source,
                            created_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                        )
                    """, [
                        str(uuid.uuid4()),
                        provider,
                        model,
                        prompt,  # ИСПРАВЛЕНО (2026-02-05): Полный промпт без обрезки
                        response_to_save,
                        usage_info['prompt_tokens'],
                        usage_info['completion_tokens'],
                        usage_info['total_tokens'],
                        usage_info['cost_rub'],
                        session_id,  # ИСПРАВЛЕНО (2026-01-06): session_id
                        message_id,  # ИСПРАВЛЕНО (2026-01-06): message_id
                        caller_service,
                        prompt_slug,
                        prompt_source
                    ])

            await sync_to_async(save_sync)()
            logger.info(f"[LLM-STAT] УСПЕХ: Статистика сохранена в БД (provider={provider}, model={model})")

        except Exception as e:
            logger.error(f"Ошибка при сохранении статистики в БД: {e}")
            # Не прерываем работу если статистика не сохранилась

    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику использования"""
        return {
            'total_requests': self.stats['total_requests'],
            'total_tokens': self.stats['total_tokens'],
            'total_cost_rub': round(self.stats['total_cost'], 2),
            'yandexgpt': {
                'requests': self.stats['yandexgpt']['requests'],
                'tokens': self.stats['yandexgpt']['tokens'],
                'cost_rub': round(self.stats['yandexgpt']['cost'], 2)
            },
            'gigachat': {
                'requests': self.stats['gigachat']['requests'],
                'tokens': self.stats['gigachat']['tokens'],
                'cost_rub': round(self.stats['gigachat']['cost'], 2)
            }
        }

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

        prompt = f"""Ты - диспетчер управляющей компании (УК). Твоя задача - определить, какую услугу запрашивает абонент.

ДОСТУПНЫЕ УСЛУГИ:
{services_text}

СООБЩЕНИЕ АБОНЕНТА:
"{message_text}"

ПРАВИЛА:
- Проанализируй сообщение и сопоставь с доступными услугами
- Если однозначно определяешь услугу - верни её ID и название
- Если НЕ однозначно - задай ОДИН открытый уточняющий вопрос
- Вопрос должен быть кратким, конкретным и естественным
- НЕ используй эмодзи
- Используй простую разговорную речь

ОТВЕТ В ФОРМАТЕ JSON:
{{
  "status": "SUCCESS" или "AMBIGUOUS",
  "service_id": 123,
  "service_name": "Название услуги",
  "question": "Уточняющий вопрос (если status=AMBIGUOUS)",
  "confidence": 0.95
}}
"""
        return prompt

    async def detect_service(self, message: str, session_id: str = None) -> Dict[str, Any]:
        """
        Определить услугу по сообщению

        Args:
            message: Сообщение пользователя

        Returns:
            {
                'status': 'SUCCESS' | 'AMBIGUOUS',
                'service_id': 123,
                'service_name': '...',
                'question': '...',
                'confidence': 0.95,
                'usage': {...}
            }
        """
        await self._load_services()
        prompt = self._create_service_detection_prompt(message)

        # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
        response, usage = await self.call_llm(prompt, session_id=session_id)

        try:
            result = json.loads(response)
            result['usage'] = usage
            return result
        except json.JSONDecodeError:
            logger.error(f"Ошибка парсинга JSON от LLM: {response}")
            return {
                'status': 'ERROR',
                'error': 'Invalid JSON response',
                'raw_response': response,
                'usage': usage
            }

    async def get_embedding(self, text: str, model: str = 'text-search-doc') -> Tuple[List[float], Dict[str, Any]]:
        """
        Получить embedding от Yandex API

        ИСПРАВЛЕНО (2026-01-13):
        - Добавлен метод для генерации embeddings через Yandex API
        - Отдельное логирование стоимости от LLM промптов
        - Статистика по embeddings в self.stats['embeddings']

        Args:
            text: Текст для векторизации
            model: Модель embeddings (text-search-doc по умолчанию)

        Returns:
            (embedding_vector, usage_info)
            - embedding_vector: List[float] длиной 256
            - usage_info: Dict с информацией о вызове

        Raises:
            Exception: Ошибка API или недоступность Yandex

        Пример:
            vector, usage = await service.get_embedding("прорыв канализации")
            print(len(vector))  # 256
            print(usage['cost_rub'])  # 0.0012
        """
        if not self.yandexgpt_available:
            raise Exception("Yandex Embeddings недоступен (не настроен API key или folder ID)")

        try:
            import aiohttp

            # URL для Yandex Embeddings API
            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

            # Headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {self.yandexgpt_api_key}",
                "x-folder-id": self.yandexgpt_folder_id
            }

            # Payload
            payload = {
                "modelUri": f"emb://{self.yandexgpt_folder_id}/text-search-doc/latest",
                "text": text
            }

            logger.debug(f"AIAgentService: Yandex Embeddings REQUEST text='{text[:100]}...'")

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30.0)) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    logger.info(f"AIAgentService: Yandex Embeddings API response: {response.status}")

                    if response.status == 200:
                        result = await response.json()

                        # Извлекаем embedding вектор
                        embedding = result.get("embedding", [])

                        if not embedding:
                            raise Exception("Пустой embedding в ответе")

                        # Рассчитываем количество токенов (примерно: 1 токен = 4 символа для русского)
                        estimated_tokens = max(1, len(text) // 4)

                        # Рассчитываем стоимость
                        price_per_1k = self.YANDEX_EMBEDDING_PRICES.get(model, 0.10)
                        cost = (estimated_tokens / 1000) * price_per_1k

                        # Формируем usage_info
                        usage_info = {
                            'provider': 'yandex',
                            'service': 'embeddings',
                            'model': model,
                            'text_length': len(text),
                            'estimated_tokens': estimated_tokens,
                            'embedding_dimension': len(embedding),
                            'cost_rub': round(cost, 6),
                            'cost_per_1k_tokens': price_per_1k
                        }

                        # Логирование
                        logger.info(
                            f"AIAgentService: Yandex Embeddings завершен. "
                            f"Длина текста: {len(text)} символов, "
                            f"размерность: {len(embedding)}, "
                            f"стоимость: {cost:.6f} руб."
                        )

                        # Обновляем статистику
                        self.stats['embeddings']['requests'] += 1
                        self.stats['embeddings']['tokens'] += estimated_tokens
                        self.stats['embeddings']['cost'] += cost
                        self.stats['total_requests'] += 1
                        self.stats['total_cost'] += cost

                        return embedding, usage_info

                    else:
                        # Ошибка API
                        error_text = await response.text()
                        logger.error(f"Yandex Embeddings API error {response.status}: {error_text}")
                        raise Exception(f"Yandex Embeddings API error {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Ошибка при вызове Yandex Embeddings: {e}")
            raise
