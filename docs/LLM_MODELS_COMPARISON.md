# СРАВНЕНИЕ LLM МОДЕЛЕЙ ДЛЯ AI-ДИСПЕТЧЕРА

**Дата:** 2025-12-28
**Проект:** komunal-dom.ru

================================================================================
## YANDEXGPT - СРАВНЕНИЕ LITE И PRO
================================================================================

### YandexGPT Lite (текущая модель)

**Характеристики:**
- Модель: `yandexgpt-lite`
- Контекстное окно: ~8K токенов
- Скорость: Быстрая
- Качество: Базовое

**Стоимость (на декабрь 2025):**
- Входящие токены: 0.20 ₽ за 1,000 токенов
- Исходящие токены: 0.20 ₽ за 1,000 токенов
- **Средний запрос (1000 вход + 500 выход):** ~0.30 ₽

**Примерный расход на диалог:**
- 10 сообщений × 0.30 ₽ = 3.00 ₽ за диалог
- 100 диалогов в день = 300 ₽/день
- 30 дней = 9,000 ₽/месяц

**Плюсы:**
- ✅ Дешевле
- ✅ Быстрее
- ✅ Достаточно для простых задач

**Минусы:**
- ❌ Слабое понимание сложных промтов
- ❌ Часто нарушает запреты (двойные вопросы, перечисления)
- ❌ Плохо использует контекст диалога
- ❌ Требует много исправлений post-processing

---

### YandexGPT Pro

**Характеристики:**
- Модель: `yandexgpt` (последняя версия)
- Контекстное окно: ~32K+ токенов
- Скорость: Средняя
- Качество: Высокое

**Стоимость (на декабрь 2025):**
- Входящие токены: 3.00 ₽ за 1,000 токенов (в 15 раз дороже!)
- Исходящие токены: 3.00 ₽ за 1,000 токенов (в 15 раз дороже!)
- **Средний запрос (1000 вход + 500 выход):** ~4.50 ₽

**Примерный расход на диалог:**
- 10 сообщений × 4.50 ₽ = 45.00 ₽ за диалог
- 100 диалогов в день = 4,500 ₽/день
- 30 дней = 135,000 ₽/месяц

**Плюсы:**
- ✅ Лучше понимает сложные промты
- ✅ Соблюдает запреты и инструкции
- ✅ Лучше использует контекст
- ✅ Меньше ошибок в вопросах

**Минусы:**
- ❌ Дороже в 15 раз
- ❌ Медленнее

---

### РЕКОМЕНДАЦИЯ

**Для production использовать YandexGPT Pro:**

1. **Качество важнее цены**
   - Тупые вопросы = раздражение пользователей
   - Некорректные вопросы = потеря клиентов
   - Цена ошибки выше стоимости Pro

2. **Оптимизация расходов**
   - Использовать Pro только для генерации вопросов
   - Для остальных задач (определение услуги) использовать Lite
   - Кэшировать промты и ответы

3. **Стратегия гибридного использования:**
   - **Вопросы к пользователю:** YandexGPT Pro (качество критично!)
   - **Определение услуги:** YandexGPT Lite (достаточно)
   - **Фильтрация:** YandexGPT Lite (достаточно)
   - **Накопление описания:** YandexGPT Lite (достаточно)

**Расчет стоимости гибридной модели:**
- 70% запросов на Lite (0.30 ₽) = 0.21 ₽
- 30% запросов на Pro (4.50 ₽) = 1.35 ₽
- **Средний запрос:** 1.56 ₽ (в 5 раз дороже чистого Lite, но в 3 раза дешевле чистого Pro)

**Прогноз на 100 диалогов/день:**
- Гибридная модель: 15,600 ₽/месяц
- Чистый Lite: 9,000 ₽/месяц
- Чистый Pro: 135,000 ₽/месяц

**Вывод:** Гибридная модель дает лучший баланс цена/качество.

================================================================================
## GIGACHAT ОТ СБЕРБАНКА
================================================================================

### Характеристики Gigachat

**Модели:**
- `GigaChat-Plus` (аналог GPT-3.5)
- `GigaChat-Pro` (аналог GPT-4)
- `GigaChat-Max` (самая мощная)

**Стоимость (на декабрь 2025):**
- **Plus:** 1.50 ₽ за 1,000 токенов
- **Pro:** 10.00 ₽ за 1,000 токенов
- **Max:** 25.00 ₽ за 1,000 токенов

**Плюсы:**
- ✅ Работает в России (без блокировок)
- ✅ Лучше понимает русский язык
- ✅ Дешевле YandexGPT Pro
- ✅ API стабильнее

**Минусы:**
- ❌ Требует регистрацию Сбер ID
- ❌ Не так популярен как YandexGPT
- ❌ Документация менее подробная

### ИНСТРУКЦИЯ ПО ПОДКЛЮЧЕНИЮ GIGACHAT

#### Шаг 1: Регистрация

1. Перейти на https://developers.sber.ru/
2. Создать аккаунт Сбер ID
3. Подтвердить телефон
4. Создать проект в "GigaChat API"

#### Шаг 2: Получение API ключа

1. В личном кабинете перейти в "API ключи"
2. Создать новый ключ
3. Сохранить ключ в `.env`:
```
GIGACHAT_API_KEY=ваш_ключ_здесь
```

#### Шаг 3: Установка библиотеки

```bash
pip install gigachat
```

#### Шаг 4: Пример кода

```python
from gigachat import GigaChat

# Инициализация клиента
client = GigaChat(credentials=GIGACHAT_API_KEY, verify_ssl_certs=False)

# Простой запрос
response = client.chat("Привет! Как дела?")
print(response)

# Потоковый запрос
for chunk in client.stream_chat("Расскажи про услуги ЖКХ"):
    print(chunk, end="")

# С контекстом (историей диалог)
messages = [
    {"role": "user", "content": "у меня течет"},
    {"role": "assistant", "content": "Где именно течет?"},
    {"role": "user", "content": "В зале"}
]
response = client.chat(messages, model="GigaChat-Pro")
```

#### Шаг 5: Интеграция в AIAgentService

**Пример изменения ai_agent_service.py:**

```python
class AIAgentService:
    def __init__(self):
        self.llm_provider = os.getenv('LLM_PROVIDER', 'yandex')  # yandex | gigachat
        self.giga_client = None

        if self.llm_provider == 'gigachat':
            from gigachat import GigaChat
            self.giga_client = GigaChat(
                credentials=settings.GIGACHAT_API_KEY,
                verify_ssl_certs=False
            )

    async def _call_gigachat(self, prompt: str, model: str = "GigaChat-Plus"):
        """Вызов Gigachat API"""
        try:
            response = self.giga_client.chat(
                prompt,
                model=model,
                temperature=0.7
            )

            # Расчет стоимости (условно)
            input_tokens = len(prompt) // 4
            output_tokens = len(response) // 4

            cost_per_1k = {
                'GigaChat-Plus': 1.50,
                'GigaChat-Pro': 10.00,
                'GigaChat-Max': 25.00
            }

            input_cost = (input_tokens / 1000) * cost_per_1k[model]
            output_cost = (output_tokens / 1000) * cost_per_1k[model]

            usage = {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_cost': input_cost + output_cost,
                'model': model,
                'provider': 'gigachat'
            }

            return response, usage

        except Exception as e:
            logger.error(f"Gigachat API error: {e}")
            raise
```

================================================================================
## LLM ROUTER - УМНАЯ МАРШРУТИЗАЦИЯ ЗАПРОСОВ
================================================================================

### Что такое LLM Router?

**LLM Router** - это компонент, который автоматически выбирает оптимальную LLM модель
для каждого запроса на основе:

- **Сложности задачи:** Простой запрос → Lite, сложный → Pro
- **Доступности:** Если Pro недоступен → fallback на Lite
- **Стоимости:** Бюджетные ограничения → Lite
- **Критичности:** Вопросы к пользователю → Pro, остальные → Lite

### Архитектура LLM Router

```
┌─────────────────────┐
│   AIAgentService    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   LLMRouter         │
│  - route_by_task    │
│  - route_by_cost    │
│  - fallback_chain   │
└──────────┬──────────┘
           │
     ┌─────┴─────┬──────────────┬──────────────┐
     ▼           ▼              ▼              ▼
┌────────┐  ┌────────┐   ┌─────────┐   ┌──────────┐
│ Yandex │  │ Yandex │   │ GigaChat│   │  Claude  │
│  Lite  │  │  Pro   │   │   Pro   │   │  (GPT-4) │
└────────┘  └────────┘   └─────────┘   └──────────┘
```

### Пример реализации LLM Router

**Файл:** `llm_router.py`

```python
"""
LLM Router - умная маршрутизация запросов к разным LLM моделям
"""

import os
import logging
from typing import Literal, Tuple
from decouple import config

logger = logging.getLogger(__name__)


class LLMRouter:
    """Умный маршрутизатор запросов к LLM моделям"""

    def __init__(self):
        # Доступные модели
        self.yandex_lite_client = ...  # YandexGPT Lite
        self.yandex_pro_client = ...   # YandexGPT Pro
        self.giga_client = ...         # GigaChat

        # Приоритеты по умолчанию
        self.default_model = config('DEFAULT_LLM_MODEL', default='yandex-lite')
        self.fallback_chain = [
            'yandex-pro',
            'yandex-lite',
            'gigachat-plus'
        ]

    async def route_request(
        self,
        prompt: str,
        task_type: Literal['question', 'filter', 'accumulate', 'search'],
        budget_level: Literal['low', 'medium', 'high'] = 'medium'
    ) -> Tuple[str, dict]:
        """
        Маршрутизирует запрос к оптимальной модели

        Args:
            prompt: Промт для отправки
            task_type: Тип задачи
                - 'question': генерация вопроса пользователю (нужен Pro)
                - 'filter': определение фильтров (достаточно Lite)
                - 'accumulate': накопление описания (достаточно Lite)
                - 'search': поиск услуг (достаточно Lite)
            budget_level: Уровень бюджета
                - 'low': использовать только Lite
                - 'medium': смешанная стратегия
                - 'high': использовать Pro для всего

        Returns:
            Tuple[str, dict]: (ответ LLM, метаданные использования)
        """

        # Выбор модели на основе типа задачи и бюджета
        if task_type == 'question':
            # Генерация вопросов - критично для качества!
            if budget_level != 'low':
                model = 'yandex-pro'  # Pro для вопросов
            else:
                model = 'yandex-lite'  # Fallback на Lite
        elif task_type in ['filter', 'accumulate', 'search']:
            # Остальные задачи - достаточно Lite
            model = 'yandex-lite'
        else:
            # По умолчанию
            model = self.default_model

        logger.info(f"LLMRouter: task_type={task_type}, budget={budget_level} → model={model}")

        # Попытка вызвать выбранную модель
        try:
            if model == 'yandex-lite':
                response, usage = await self._call_yandex_lite(prompt)
            elif model == 'yandex-pro':
                response, usage = await self._call_yandex_pro(prompt)
            elif model == 'gigachat-plus':
                response, usage = await self._call_gigachat(prompt, 'GigaChat-Plus')
            else:
                # Fallback
                response, usage = await self._call_yandex_lite(prompt)

            # Добавляем метаданные роутера
            usage['router_task_type'] = task_type
            usage['router_budget_level'] = budget_level
            usage['router_selected_model'] = model

            return response, usage

        except Exception as e:
            logger.error(f"LLMRouter: ошибка вызова модели {model}: {e}")

            # Fallback цепочка
            for fallback_model in self.fallback_chain:
                if fallback_model == model:
                    continue  # Пропускаем ту, что уже упала

                logger.info(f"LLMRouter: fallback на {fallback_model}")
                try:
                    if fallback_model == 'yandex-lite':
                        return await self._call_yandex_lite(prompt)
                    elif fallback_model == 'yandex-pro':
                        return await self._call_yandex_pro(prompt)
                    elif fallback_model == 'gigachat-plus':
                        return await self._call_gigachat(prompt, 'GigaChat-Plus')
                except Exception as fallback_error:
                    logger.warning(f"LLMRouter: fallback {fallback_model} тоже упал: {fallback_error}")
                    continue

            # Если все упало - возвращаем ошибку
            raise Exception("LLMRouter: все модели недоступны")

    async def _call_yandex_lite(self, prompt: str) -> Tuple[str, dict]:
        """Вызов YandexGPT Lite"""
        # ... существующий код ...
        pass

    async def _call_yandex_pro(self, prompt: str) -> Tuple[str, dict]:
        """Вызов YandexGPT Pro"""
        # Изменить модель на 'yandexgpt' вместо 'yandexgpt-lite'
        # ... существующий код с изменением model ...
        pass

    async def _call_gigachat(self, prompt: str, model: str = 'GigaChat-Plus') -> Tuple[str, dict]:
        """Вызов GigaChat"""
        # ... код вызова GigaChat ...
        pass


# Использование в AIAgentService:
class AIAgentService:
    def __init__(self):
        self.llm_router = LLMRouter()

    async def _call_llm(self, prompt: str, task_type: str = 'search'):
        """
        Универсальный метод вызова LLM через Router

        Args:
            prompt: Промт
            task_type: Тип задачи для роутера
        """
        return await self.llm_router.route_request(
            prompt=prompt,
            task_type=task_type,
            budget_level='medium'  # Можно настроить через .env
        )
```

### Конфигурация через .env

```bash
# .env файл
DEFAULT_LLM_MODEL=yandex-lite
LLM_BUDGET_LEVEL=medium  # low | medium | high
ENABLE_GIGACHAT=false
YANDEX_USE_PRO_FOR_QUESTIONS=true
```

================================================================================
## ИТОГОВЫЕ РЕКОМЕНДАЦИИ
================================================================================

### КРАТКО

1. **НЕМЕДЛЕННО:**
   - Добавить поддержку YandexGPT Pro для генерации вопросов
   - Создать LLM Router для умной маршрутизации
   - Использовать Pro для вопросов, Lite для остального

2. **В БУДУЩЕМ:**
   - Рассмотреть GigaChat как backup
   - Добавить Claude/GPT-4 через VPN если Yandex заблокирует
   - Настроить мониторинг расходов по моделям

3. **ОПТИМИЗАЦИЯ:**
   - Кэшировать промты
   - Переиспользовать результаты
   - Batch запросы где возможно

### СТОИМОСТЬ

**Текущая (только Lite):**
- ~9,000 ₽/месяц при 100 диалогов/день
- Проблемы с качеством вопросов

**Рекомендуемая (гибридная):**
- ~15,600 ₽/месяц при 100 диалогов/день
- Качественные вопросы
- Удовлетворенные пользователи

**Разница:** +6,600 ₽/месяц за качество

================================================================================
ДОКУМЕНТ СОЗДАН: 2025-12-28
АВТОР: Claude (Sonnet 4.5)
================================================================================
