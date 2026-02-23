# GigaChat Fallback Proposal

## Задача
Создать fallback-механизм на случай недоступности основного LLM (YandexGPT)

## Рекомендация: GigaChat от Сбера

### Преимущества
- ✅ Российский сервис (Сбер)
- ✅ Оплата в рублях с российских карт
- ✅ API похож на OpenAI (chat completion формат)
- ✅ Доступен из России без VPN
- ✅ Competitive pricing (~0.5-1 руб за 1000 токенов)

### Регистрация
1. https://developers.sber.ru/docs/ru/gigachat/
2. Создать приложение
3. Получить API ключ
4. Пополнить баланс с российской карты

### Пример кода

```python
class GigaChatService:
    """Fallback LLM сервис на базе GigaChat"""

    BASE_URL = "https://gigachat.devices.sbercloud.ru/api/v1"

    def __init__(self):
        self.api_key = config('GIGACHAT_API_KEY')
        self.is_available = bool(self.api_key)

    async def call_llm(self, prompt: str) -> str:
        """Вызов GigaChat API"""
        import httpx

        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': 'GigaChat',
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': 0.7
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
```

### Интеграция в AIAgentService

```python
class AIAgentService:
    def __init__(self):
        self.primary_llm = YandexGPTService()
        self.fallback_llm = GigaChatService()

    async def _call_yandex_gpt(self, prompt):
        try:
            return await self.primary_llm.call(prompt)
        except Exception as e:
            logger.warning(f"YandexGPT failed: {e}, trying GigaChat")
            return await self.fallback_llm.call(prompt)
```

## Альтернативы

1. **YandexGPT** - можно использовать как fallback сам к себе (повторный вызов)
2. **OpenRouter** - агрегатор моделей, принимает российские карты
3. **Claude** - через посредников (дорого)

## Стоимость

- YandexGPT: ~0.20 руб / 1000 токенов
- GigaChat: ~0.50-1.00 руб / 1000 токенов
- OpenRouter: зависит от модели

## Приоритет

1. **YandexGPT** (основной)
2. **GigaChat** (fallback #1)
3. **Повторный YandexGPT** (fallback #2)
