#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenRouterFallbackService - fallback LLM сервис через OpenRouter

Поддерживает множество моделей через единый API:
- GPT-3.5/4 от OpenAI
- Claude от Anthropic
- И многие другие

Документация: https://openrouter.ai/docs
"""

import logging
import httpx
from typing import Optional
from decouple import config

logger = logging.getLogger(__name__)


class OpenRouterFallbackService:
    """Fallback LLM сервис через OpenRouter"""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self):
        self.api_key = config('OPENROUTER_API_KEY', default=None)
        self.is_available = bool(self.api_key)

        # Модель по умолчанию
        self.model = config('OPENROUTER_MODEL', default='openai/gpt-3.5-turbo')

        if self.is_available:
            logger.info(f"OpenRouterFallbackService инициализирован (model: {self.model})")
        else:
            logger.warning("OpenRouterFallbackService не доступен (нет API ключа)")

    async def call_llm(self, prompt: str, temperature: float = 0.7) -> Optional[str]:
        """
        Вызов LLM через OpenRouter

        Args:
            prompt: Текст промпта
            temperature: Температура генерации (0.0-1.0)

        Returns:
            str: Ответ LLM или None при ошибке
        """
        if not self.is_available:
            logger.error("OpenRouterFallbackService недоступен")
            return None

        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://komunal-dom.ru',  # Требуется OpenRouter
                'X-Title': 'Komunal-Dom Bot'
            }

            payload = {
                'model': self.model,
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': temperature,
                'max_tokens': 1000
            }

            logger.info(f"OpenRouter: отправляем запрос (model: {self.model}, prompt длиной: {len(prompt)} символов)")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

                result = response.json()

                if 'choices' in result and len(result['choices']) > 0:
                    answer = result['choices'][0]['message']['content']

                    # Логируем использование токенов
                    if 'usage' in result:
                        tokens = result['usage']
                        logger.info(
                            f"OpenRouter: получен ответ. "
                            f"Токены: {tokens.get('prompt_tokens', 0)} вх + {tokens.get('completion_tokens', 0)} вых = {tokens.get('total_tokens', 0)} всего"
                        )

                    return answer
                else:
                    logger.error(f"OpenRouter: неожиданный ответ: {result}")
                    return None

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter: HTTP ошибка {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"OpenRouter: ошибка вызова: {e}")
            return None

    def get_pricing_info(self) -> dict:
        """
        Информация о ценах на моделях

        Returns:
            dict: Цены на популярные модели
        """
        return {
            'openai/gpt-3.5-turbo': '~$0.50 / 1M токенов (через OpenRouter)',
            'openai/gpt-4o': '~$5.00 / 1M токенов (через OpenRouter)',
            'anthropic/claude-3-haiku': '~$0.25 / 1M токенов (через OpenRouter)',
            'anthropic/claude-3.5-sonnet': '~$3.00 / 1M токенов (через OpenRouter)',
            'Ссылка': 'https://openrouter.ai/models?order=newest&pricing=free'
        }


# ============================================================================
# ИНТЕГРАЦИЯ В AIAgentService
# ============================================================================

def integrate_openrouter_fallback():
    """
    Инструкции по интеграции OpenRouter как fallback в AIAgentService

    1. Добавить в __init__ AIAgentService:
       ```python
       from openrouter_fallback import OpenRouterFallbackService

       def __init__(self):
           # ... существующий код ...
           self.fallback_llm = OpenRouterFallbackService()
       ```

    2. Изменить метод _call_yandex_gpt:
       ```python
       async def _call_yandex_gpt(self, prompt: str):
           try:
               # Сначала пробуем YandexGPT
               return await self._call_yandex_internal(prompt)
           except Exception as e:
               logger.warning(f"YandexGPT failed: {e}, trying OpenRouter fallback")
               if self.fallback_llm.is_available:
                   response = await self.fallback_llm.call_llm(prompt)
                   if response:
                       usage_info = {'fallback': 'openrouter'}
                       return response, usage_info
               raise  # Re-raise если fallback тоже не сработал
       ```
    """
    pass
