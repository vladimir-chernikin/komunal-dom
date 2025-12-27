#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ИНСТРУКЦИЯ ПО ИНТЕГРАЦИИ FALLBACK В AIAgentService

Этот файл содержит готовый код для добавления fallback механизма
в AIAgentService для переключения на OpenRouter или GigaChat
при недоступности YandexGPT.
"""

# ============================================================================
# ШАГ 1: Добавить импорты в ai_agent_service.py
# ============================================================================

# Добавить в начало файла ai_agent_service.py после существующих импортов:

```python
from openrouter_fallback import OpenRouterFallbackService
# от GigaChat при желании:
# from gigachat_service import GigaChatService
```

# ============================================================================
# ШАГ 2: Инициализировать fallback сервисы в __init__
# ============================================================================

# В методе __init__ класса AIAgentService добавить после строки 36:

```python
def __init__(self):
    # ... существующий код ...

    # Инициализация fallback сервисов
    self.fallback_llm = OpenRouterFallbackService()
    # self.fallback_llm2 = GigaChatService()  # Опционально

    logger.info(f"AIAgentService инициализирован (доступен: {self.is_available})")
    logger.info(f"OpenRouter fallback: {'доступен' if self.fallback_llm.is_available else 'недоступен'}")
```

# ============================================================================
# ШАГ 3: Создать метод _call_with_fallback
# ============================================================================

# Добавить новый метод в класс AIAgentService (после метода _call_yandex_gpt):

```python
async def _call_with_fallback(self, prompt: str) -> tuple:
    """
    Вызов LLM с fallback на случай ошибки YandexGPT

    Приоритет:
    1. YandexGPT (основной)
    2. OpenRouter (fallback #1)
    3. Повторный YandexGPT (fallback #2)

    Args:
        prompt: Текст промпта

    Returns:
        tuple: (response_text, usage_info) или (None, None) при полной ошибке
    """
    # ПЕРВИЧНЫЙ: YandexGPT
    try:
        logger.info("Пытаемся вызвать YandexGPT (основной)")
        return await self._call_yandex_gpt(prompt)
    except Exception as e:
        logger.warning(f"YandexGPT failed: {e}")

    # FALLBACK 1: OpenRouter
    if self.fallback_llm.is_available:
        try:
            logger.info("Используем OpenRouter fallback")
            response = await self.fallback_llm.call_llm(prompt)

            if response:
                # Формируем usage_info в формате совместимом с YandexGPT
                usage_info = {
                    'prompt_tokens': len(prompt) // 4,  # Примерная оценка
                    'completion_tokens': len(response) // 4,
                    'total_tokens': (len(prompt) + len(response)) // 4,
                    'fallback': 'openrouter',
                    'model': self.fallback_llm.model
                }
                return response, usage_info
            else:
                logger.error("OpenRouter вернул пустой ответ")

        except Exception as e2:
            logger.error(f"OpenRouter fallback failed: {e2}")

    # FALLBACK 2: Повторный YandexGPT (иногда помогает при временных сбоях)
    try:
        logger.info("Повторная попытка YandexGPT")
        return await self._call_yandex_gpt(prompt)
    except Exception as e3:
        logger.error(f"Повторный YandexGPT failed: {e3}")

    # Все fallback'ы исчерпаны
    logger.error("ВСЕ LLM СЕРВИСЫ НЕДОСТУПНЫ!")
    return None, None
```

# ============================================================================
# ШАГ 4: Заменить вызовы _call_yandex_gpt на _call_with_fallback
# ============================================================================

# В методах AIAgentService заменить:
#   response, usage = await self._call_yandex_gpt(prompt)
# на:
#   response, usage = await self._call_with_fallback(prompt)

# Методы для замены:
# - detect_service() (строка ~170)
# - detect_category() (если есть)

# ============================================================================
# ШАГ 5: Обновить логирование для indicate fallback
# ============================================================================

# В методе _log_api_call добавить обработку fallback:

```python
def _log_api_call(self, prompt_length: int, response_length: int, usage_info: dict = None):
    """Логирование вызова API с указанием используемого сервиса"""

    model = usage_info.get('model', 'yandexgpt-lite') if usage_info else 'yandexgpt-lite'
    fallback = usage_info.get('fallback', None) if usage_info else None

    if fallback:
        logger.info(f"FALLBACK использован: {fallback} (model: {model})")

    prompt_cost = prompt_length * self.PRICE_INPUT_PER_1K / 1000
    response_cost = response_length * self.PRICE_OUTPUT_PER_1K / 1000
    total_cost = prompt_cost + response_cost

    logger.info(
        f"API вызов завершен. Токены: {prompt_length} вх + {response_length} вых = "
        f"{prompt_length + response_length} всего. Стоимость: {prompt_cost:.4f} + "
        f"{response_cost:.4f} = {total_cost:.4f} руб."
    )
```

# ============================================================================
# ПРИМЕР ИСПОЛЬЗОВАНИЯ В FilterDetectionService
# ============================================================================

# В filter_detection_service.py заменить:
#
#   response, usage_info = await self.ai_agent._call_yandex_gpt(prompt)
#
# на:
#
#   response, usage_info = await self.ai_agent._call_with_fallback(prompt)

# ============================================================================
# ТЕСТИРОВАНИЕ FALLBACK
# ============================================================================

"""
Для тестирования fallback механизма:

1. ВРЕМЕННО сломать YandexGPT в ai_agent_service.py:

```python
async def _call_yandex_gpt(self, prompt: str) -> tuple:
    # ИСКУССТВЕННЫЙ СБОЙ ДЛЯ ТЕСТА FALLBACK:
    raise Exception("Тестовый сбой YandexGPT")
```

2. Убедиться что в .env есть:
   OPENROUTER_API_KEY=sk-or-v1-ваш_ключ
   OPENROUTER_MODEL=openai/gpt-3.5-turbo

3. Запустить тест:
   python test_bot_simulator.py

4. В логах должно быть:
   - "YandexGPT failed: Тестовый сбой YandexGPT"
   - "Используем OpenRouter fallback"
   - "FALLBACK использован: openrouter"

5. Убрать искусственный сбой и вернуть нормальный код
"""

# ============================================================================
# КОНТРОЛЬНЫЙ ЧЕК-ЛИСТ ИНТЕГРАЦИИ
# ============================================================================

"""
✅ Шаг 1: Импорты добавлены в ai_agent_service.py
✅ Шаг 2: Fallback сервисы инициализированы в __init__
✅ Шаг 3: Метод _call_with_fallback создан
✅ Шаг 4: Все вызовы _call_yandex_gpt заменены на _call_with_fallback
✅ Шаг 5: Логирование обновлено для indicate fallback
✅ Шаг 6: FilterDetectionService использует _call_with_fallback
✅ Шаг 7: .env содержит OPENROUTER_API_KEY
✅ Шаг 8: Проведено тестирование fallback механизма
"""

# ============================================================================
# ДИАГНОСТИКА ПРИБЛЕМ
# ============================================================================

"""
ПРОБЛЕМА: OpenRouter недоступен
РЕШЕНИЕ: Проверить что OPENROUTER_API_KEY задан в .env

ПРОБЛЕМА: Fallback не срабатывает при ошибке YandexGPT
РЕШЕНИЕ: Проверить что все вызовы _call_yandex_gpt заменены на _call_with_fallback

ПРОБЛЕМА: Нет логов "Используем OpenRouter fallback"
РЕШЕНИЕ: Проверить что self.fallback_llm.is_available == True

ПРОБЛЕМА: Ответ от OpenRouter пустой
РЕШЕНИЕ: Проверить баланс на аккаунте OpenRouter и валидность API ключа
"""
