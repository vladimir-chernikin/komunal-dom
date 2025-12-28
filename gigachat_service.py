"""
GigaChat Service - Сервис для работы с GigaChat API от Сбербанка

Дата создания: 2025-12-28
Назначение: Единый сервис для вызовов LLM GigaChat с поддержкой разных моделей

Авторизация:
- Client ID: 019b65dd-feb9-756f-a83e-330d88d76fa0
- Scope: GIGACHAT_API_PERS
- Authorization Key: MDE5YjY1ZGQtZmViOS03NTZmLWE4M2UtMzMwZDg4ZDc2ZmEwOjYyODNjZGRiLTBiNGYtNDZhMS04NDVlLWZjOTYyYWE2ZWFiYg==

Документация:
- https://developers.sber.ru/docs/ru/gigachain/overview
- https://github.com/ai-forever/gigachat
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from datetime import timezone

import httpx

# Настройка логирования
logger = logging.getLogger(__name__)


class GigaChatModel:
    """Описание доступных моделей GigaChat"""

    MODELS = {
        "GigaChat": {
            "name": "GigaChat",
            "description": "Базовая модель",
            "cost_per_1k_tokens": 0.50,  # примерная стоимость
            "context_length": 8192,
            "use_case": "Простые задачи, классификация, извлечение сущностей"
        },
        "GigaChat-2": {
            "name": "GigaChat-2",
            "description": "Улучшенная модель (версия 2.0)",
            "cost_per_1k_tokens": 1.50,
            "context_length": 16384,
            "use_case": "Сложные задачи, анализ текста, многошаговые рассуждения"
        },
        "GigaChat-Plus": {
            "name": "GigaChat-Plus",
            "description": "Самая мощная модель",
            "cost_per_1k_tokens": 3.00,
            "context_length": 32768,
            "use_case": "Наиболее сложные задачи, генерация кода, глубокий анализ"
        },
        "GigaChat-2.1": {
            "name": "GigaChat-2.1",
            "description": "Обновленная модель GigaChat-2",
            "cost_per_1k_tokens": 1.80,
            "context_length": 16384,
            "use_case": "Оптимизированная версия для продакшн задач"
        }
    }

    @classmethod
    def get_model_info(cls, model_name: str) -> Dict[str, Any]:
        """Получить информацию о модели"""
        return cls.MODELS.get(model_name, cls.MODELS["GigaChat"])

    @classmethod
    def get_all_models(cls) -> Dict[str, Dict[str, Any]]:
        """Получить список всех моделей"""
        return cls.MODELS

    @classmethod
    def recommend_model(cls, task_complexity: str = "simple") -> str:
        """
        Рекомендовать модель на основе сложности задачи

        Args:
            task_complexity: simple | medium | complex
        """
        if task_complexity == "simple":
            return "GigaChat"
        elif task_complexity == "medium":
            return "GigaChat-2"
        else:  # complex
            return "GigaChat-Plus"


class GigaChatService:
    """
    Сервис для работы с GigaChat API

    Особенности:
    - Автоматическое получение и обновление OAuth токена
    - Поддержка всех моделей GigaChat
    - Логирование токенов и стоимости
    - Retry логика при ошибках API
    """

    # OAuth endpoints
    OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    API_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1/"

    # Параметры авторизации
    CLIENT_ID = "019b65dd-feb9-756f-a83e-330d88d76fa0"
    AUTHORIZATION_KEY = "MDE5YjY1ZGQtZmViOS03NTZmLWE4M2UtMzMwZDg4ZDc2ZmEwOjYyODNjZGRiLTBiNGYtNDZhMS04NDVlLWZjOTYyYWE2ZWFiYg=="
    SCOPE = "GIGACHAT_API_PERS"

    def __init__(
        self,
        model: str = "GigaChat",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Инициализация сервиса

        Args:
            model: Название модели (GigaChat, GigaChat-2, GigaChat-Plus)
            timeout: Таймаут запросов в секундах
            max_retries: Максимальное количество попыток при ошибках
        """
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        # HTTP клиент с отключенной проверкой SSL (для тестов)
        self._client = httpx.AsyncClient(
            verify=False,
            timeout=timeout
        )

        logger.info(f"GigaChatService инициализирован с моделью: {self.model}")

    async def _get_access_token(self) -> str:
        """
        Получить OAuth токен доступа

        Returns:
            Access token

        Токен кешируется и автоматически обновляется при истечении срока действия
        """
        # Проверяем, есть ли валидный токен
        if self._access_token and self._token_expires_at:
            if datetime.now(timezone.utc) < self._token_expires_at:
                logger.debug("Используем кешированный токен")
                return self._access_token

        # Генерируем уникальный RqUID для каждого запроса
        rq_uid = str(uuid.uuid4())

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rq_uid,
            "Authorization": f"Basic {self.AUTHORIZATION_KEY}"
        }

        data = {
            "scope": self.SCOPE
        }

        try:
            logger.info(f"Запрос OAuth токена (RqUID: {rq_uid})")

            response = await self._client.post(
                self.OAUTH_URL,
                headers=headers,
                data=data
            )

            response.raise_for_status()
            token_data = response.json()

            self._access_token = token_data["access_token"]

            # GigaChat возвращает expires_at в миллисекундах (Unix timestamp)
            expires_at_ms = token_data.get("expires_at", 0)

            if expires_at_ms > 0:
                # Конвертируем миллисекунды в datetime
                self._token_expires_at = datetime.fromtimestamp(
                    expires_at_ms / 1000,
                    tz=timezone.utc
                ) - timedelta(minutes=1)  # За минуту до истечения
            else:
                # Fallback: 30 минут по умолчанию
                self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=1800 - 60
                )

            logger.info(
                f"OAuth токен получен успешно. "
                f"Истекает: {self._token_expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

            return self._access_token

        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка при получении токена: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при получении токена: {e}")
            raise

    async def _call_gigachat(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> tuple[str, Dict[str, Any]]:
        """
        Вызов GigaChat API

        Args:
            prompt: Промпт для LLM
            temperature: Температура (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе

        Returns:
            (response_text, usage_info)

        Raises:
            Exception: При ошибке API
        """
        try:
            # Получаем токен доступа
            access_token = await self._get_access_token()

            # Формируем запрос
            url = f"{self.API_BASE_URL}chat/completions"

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }

            logger.debug(f"Отправка запроса к GigaChat API: модель={self.model}")

            # Retry логика
            last_error = None
            for attempt in range(self.max_retries):
                try:
                    response = await self._client.post(
                        url,
                        headers=headers,
                        json=payload
                    )

                    response.raise_for_status()
                    result = response.json()

                    # Извлекаем ответ
                    response_text = result["choices"][0]["message"]["content"]

                    # Извлекаем информацию о токенах
                    usage = result.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)

                    # Рассчитываем стоимость
                    model_info = GigaChatModel.get_model_info(self.model)
                    cost_per_1k = model_info["cost_per_1k_tokens"]
                    cost_rub = (total_tokens / 1000) * cost_per_1k

                    usage_info = {
                        "model": self.model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "cost_rub": round(cost_rub, 4),
                        "cost_per_1k_tokens": cost_per_1k
                    }

                    logger.info(
                        f"GigaChat запрос завершен. "
                        f"Токенов: {total_tokens} (in: {prompt_tokens}, out: {completion_tokens}), "
                        f"стоимость: {cost_rub:.4f} руб."
                    )

                    return response_text, usage_info

                except httpx.HTTPStatusError as e:
                    last_error = e
                    if e.response.status_code == 401:
                        # Токен истек, обновляем
                        logger.warning("Токен истек, обновляем...")
                        self._access_token = None
                        self._token_expires_at = None
                        continue
                    elif e.response.status_code == 429:
                        # Rate limit, ждем и повторяем
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limit, ждем {wait_time} сек...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise

            # Если все попытки исчерпаны
            raise last_error

        except Exception as e:
            logger.error(f"Ошибка при вызове GigaChat: {e}")
            raise

    async def analyze_message(
        self,
        message: str,
        task: str = "simple"
    ) -> tuple[str, Dict[str, Any]]:
        """
        Анализ сообщения с использованием GigaChat

        Args:
            message: Текст сообщения для анализа
            task: Сложность задачи (simple/medium/complex)

        Returns:
            (analysis_result, usage_info)
        """
        # Автоматический выбор модели на основе сложности
        if task == "auto":
            task = "simple" if len(message) < 500 else "medium"

        recommended_model = GigaChatModel.recommend_model(task)

        logger.info(f"Анализ сообщения: задача={task}, модель={recommended_model}")

        # Формируем промпт для анализа
        prompt = f"""Проанализируй сообщение пользователя и извлекь ключевую информацию.

Сообщение: "{message}"

Задачи:
1. Определи тип сообщения (приветствие, проблема, вопрос, жалоба)
2. Извлеки ключевые сущности (место, объект, проблема)
3. Определи срочность

Ответ в формате JSON:
{{
  "message_type": "...",
  "entities": {{
    "location": "...",
    "object": "...",
    "problem": "..."
  }},
  "urgency": "low|medium|high",
  "summary": "Краткое описание"
}}
"""

        result, usage = await self._call_gigachat(prompt, temperature=0.3)

        return result, usage

    async def classify_service(
        self,
        message: str,
        services_list: List[str]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Классификация сообщения по списку услуг

        Args:
            message: Текст сообщения
            services_list: Список доступных услуг

        Returns:
            (classification_result, usage_info)
        """
        services_text = "\n".join([f"- {s}" for s in services_list])

        prompt = f"""Классифицируй сообщение пользователя по одной из следующих услуг:

{services_text}

Сообщение: "{message}"

Ответ в формате JSON:
{{
  "service_id": 123,
  "service_name": "Название услуги",
  "confidence": 0.95,
  "reasoning": "Обоснование выбора"
}}
"""

        result, usage = await self._call_gigachat(prompt, temperature=0.3)

        return result, usage

    async def generate_clarification_question(
        self,
        context: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """
        Генерация уточняющего вопроса

        Args:
            context: Контекст диалога (txtPrb, фильтры, кандидаты)

        Returns:
            (question, usage_info)
        """
        prompt = f"""На основе контекста диалога сгенерируй уточняющий вопрос.

Контекст:
{context}

Правила:
1. НЕ спрашивай то, что УЖЕ известно из контекста
2. Вопрос должен быть открытым (без вариантов ответа)
3. Вопрос должен быть конкретным и понятным
4. Один вопрос за раз

Сгенерируй только текст вопроса без дополнительных объяснений.
"""

        result, usage = await self._call_gigachat(prompt, temperature=0.7)

        return result, usage

    async def close(self):
        """Закрытие HTTP клиента"""
        await self._client.aclose()
        logger.info("GigaChatService закрыт")


# Примеры использования
async def main():
    """Примеры использования GigaChatService"""

    # Инициализация с базовой моделью
    service = GigaChatService(model="GigaChat")

    try:
        # Пример 1: Анализ сообщения
        message = "у меня течет труба в зале"
        result, usage = await service.analyze_message(message)

        print("Результат анализа:")
        print(result)
        print(f"\nИспользовано токенов: {usage['total_tokens']}")
        print(f"Стоимость: {usage['cost_rub']} руб.")

        # Пример 2: Получить информацию о моделях
        print("\n\nДоступные модели:")
        for model_name, model_info in GigaChatModel.get_all_models().items():
            print(f"\n{model_name}:")
            print(f"  Описание: {model_info['description']}")
            print(f"  Стоимость: {model_info['cost_per_1k_tokens']} руб./1000 токенов")
            print(f"  Контекст: {model_info['context_length']} токенов")
            print(f"  Применение: {model_info['use_case']}")

    finally:
        await service.close()


if __name__ == "__main__":
    # Запуск примеров
    asyncio.run(main())
