"""
ResponseClassifierService - Микросервис классификации ответов пользователя

НАЗНАЧЕНИЕ:
- Определяет тип ответа пользователя на вопрос бота
- Позволяет боту правильно реагировать на "я не знаю", "иди нахуй", и т.д.
- Заменяет хардкод проверки фраз на смысловой анализ через LLM

ИСПОЛЬЗУЕТ:
- YandexGPT Lite для классификации
- Контекст последнего вопроса бота

АВТОР: Claude Sonnet 4.5
ДАТА: 2026-01-06
"""

import logging
import json
from typing import Dict, Optional, List
from django.db import connection

logger = logging.getLogger(__name__)


class ResponseClassifierService:
    """
    Микросервис для классификации ответов пользователя

    Определяет тип ответа через LLM анализ:
- direct_answer - Прямой ответ на вопрос
- dont_know - Пользователь не знает ("я не знаю", "откуда я знаю")
- frustration - Разочарование/злость ("иди нахуй", "вы что тупите")
- clarification - Уточнение от пользователя
- irrelevant - Не по теме
- refusal - Отказ отвечать

    """

    # Константы типов ответов
    DIRECT_ANSWER = "direct_answer"
    DONT_KNOW = "dont_know"
    FRUSTRATION = "frustration"
    CLARIFICATION = "clarification"
    IRRELEVANT = "irrelevant"
    REFUSAL = "refusal"

    def __init__(self, ai_agent_service=None):
        """
        Инициализация сервиса

        Args:
            ai_agent_service: Экземпляр AIAgentService для вызовов LLM
        """
        self.ai_agent = ai_agent_service

    def _create_classification_prompt(
        self,
        user_response: str,
        bot_question: str,
        dialog_context: List[Dict] = None
    ) -> str:
        """
        Создание промпта для классификации ответа

        Args:
            user_response: Ответ пользователя
            bot_question: Последний вопрос бота
            dialog_context: Контекст диалога (опционально)

        Returns:
            str: Промпт для YandexGPT
        """
        # Формируем контекст
        context_text = ""
        if dialog_context and len(dialog_context) > 0:
            context_text = "\n".join([
                f"{msg.get('role', 'user')}: {msg.get('text', '')[:50]}"
                for msg in dialog_context[-3:]
            ])

        prompt = f"""Ты - аналитик который классифицирует ответы пользователей.

ПОСЛЕДНИЙ ВОПРОС БОТА:
{bot_question}

ОТВЕТ ПОЛЬЗОВАТЕЛЯ:
{user_response}

КОНТЕКСТ ДИАЛОГА (последние 3 сообщения):
{context_text}

ЗАДАЧА:
Определи ТИП ответа пользователя по следующим критериям:

1. direct_answer (ПРЯМОЙ ОТВЕТ):
   - Пользователь отвечает на вопрос бота
   - Содержит конкретную информацию
   - НЕ является "я не знаю", "откуда я знаю"
   - ПРИМЕР: "в зале", "течет труба", "батарея"

2. dont_know (НЕ ЗНАЕТ):
   - Пользователь явно говорит что НЕ знает
   - КЛЮЧЕВЫЕ ФРАЗЫ: "я не знаю", "не понимаю", "откуда я знаю", "я откуда знаю"
   - ПРИМЕР: "я не знаю", "откуда я знаю", "не понимаю о чем"

3. frustration (РАЗОЧАРОВАНИЕ/ЗЛОСТЬ):
   - Пользователь раздражен, зол, разочарован
   - КЛЮЧЕВЫЕ ФРАЗЫ: мат, "иди нахуй", "вы что тупите", "за помощью обратился", "чего вы пристаете"
   - ПРИМЕР: "иди нахуй", "вы что тупите", "за помощью обратился вы чего"

4. clarification (УТОЧНЕНИЕ):
   - Пользователь сам задает уточняющий вопрос
   - КЛЮЧЕВЫЕ СЛОВА: "а если", "а можно ли", "а есть ли"
   - ПРИМЕР: "а есть ли другие варианты", "а если это не крыша"

5. irrelevant (НЕ ПО ТЕМЕ):
   - Ответ не связан с проблемой
   - ПРИМЕР: "как погода", "привет", "спасибо"

6. refusal (ОТКАЗ):
   - Пользователь отказывается отвечать
   - ПРИМЕР: "не хочу отвечать", "зачем вам это"

ВЕРНИ JSON:
{{
  "response_type": "один из типов выше",
  "confidence": 0.0-1.0,
  "reason": "краткое обоснование"
}}

⛔ КРИТИЧЕСКИ ВАЖНО:
- АНАЛИЗИРУЙ СМЫСЛ ответа, а не ищи ключевые слова!
- "я за помощью обратился" в контексте вопроса "какие работы?" = frustration
- "откуда я знаю" после технического вопроса = dont_know
"""

        return prompt

    async def classify_response(
        self,
        user_response: str,
        bot_question: str,
        dialog_context: List[Dict] = None,
        session_id: str = None,
        message_id: int = None
    ) -> Dict:
        """
        Классификация ответа пользователя

        Args:
            user_response: Ответ пользователя
            bot_question: Последний вопрос бота
            dialog_context: Контекст диалога
            session_id: ID сессии (для логирования)
            message_id: ID сообщения (для логирования)

        Returns:
            Dict: {
                'response_type': str,  # Тип ответа
                'confidence': float,    # Уверенность 0.0-1.0
                'reason': str          # Обоснование
            }
        """
        if not self.ai_agent:
            logger.warning("ResponseClassifierService: AIAgentService не предоставлен, возвращаем direct_answer")
            return {
                'response_type': self.DIRECT_ANSWER,
                'confidence': 0.5,
                'reason': 'AIAgentService недоступен'
            }

        try:
            # Создаем промпт
            prompt = self._create_classification_prompt(
                user_response=user_response,
                bot_question=bot_question,
                dialog_context=dialog_context
            )

            # Вызываем LLM
            response_text, usage = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                temperature=0.3,  # Низкая температура для стабильной классификации
                max_tokens=200,
                session_id=session_id,
                message_id=message_id
            )

            # Парсим ответ
            result = self._parse_llm_response(response_text)

            logger.info(
                f"ResponseClassifierService: '{user_response[:40]}...' → "
                f"{result['response_type']} (confidence: {result['confidence']})"
            )

            return result

        except Exception as e:
            logger.error(f"ResponseClassifierService: Ошибка классификации: {e}")
            return {
                'response_type': self.DIRECT_ANSWER,
                'confidence': 0.0,
                'reason': f'Ошибка: {str(e)}'
            }

    def _parse_llm_response(self, response_text: str) -> Dict:
        """
        Парсинг JSON ответа от LLM

        Args:
            response_text: Ответ от YandexGPT

        Returns:
            Dict: Распарсенные данные
        """
        try:
            if not response_text:
                return {
                    'response_type': self.DIRECT_ANSWER,
                    'confidence': 0.0,
                    'reason': 'Пустой ответ'
                }

            # Ищем JSON в ответе
            json_match = response_text.find('{')
            if json_match != -1:
                json_str = response_text[json_match:]
                # Ищем закрывающую скобку
                last_brace = json_str.rfind('}')
                if last_brace != -1:
                    json_str = json_str[:last_brace + 1]
                    parsed = json.loads(json_str)

                    # Валидация response_type
                    valid_types = [
                        self.DIRECT_ANSWER,
                        self.DONT_KNOW,
                        self.FRUSTRATION,
                        self.CLARIFICATION,
                        self.IRRELEVANT,
                        self.REFUSAL
                    ]

                    response_type = parsed.get('response_type', '')
                    if response_type not in valid_types:
                        logger.warning(f"ResponseClassifierService: Неизвестный тип '{response_type}', используем direct_answer")
                        response_type = self.DIRECT_ANSWER

                    return {
                        'response_type': response_type,
                        'confidence': float(parsed.get('confidence', 0.5)),
                        'reason': parsed.get('reason', '')
                    }

            # Если не нашли JSON
            return {
                'response_type': self.DIRECT_ANSWER,
                'confidence': 0.0,
                'reason': 'Не удалось распарсить JSON'
            }

        except json.JSONDecodeError as e:
            logger.error(f"ResponseClassifierService: Ошибка парсинга JSON: {e}")
            logger.error(f"ResponseClassifierService: Ответ был: {response_text}")
            return {
                'response_type': self.DIRECT_ANSWER,
                'confidence': 0.0,
                'reason': f'JSON decode error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"ResponseClassifierService: Ошибка обработки ответа: {e}")
            return {
                'response_type': self.DIRECT_ANSWER,
                'confidence': 0.0,
                'reason': f'Error: {str(e)}'
            }

    def get_response_strategy(self, response_type: str) -> str:
        """
        Возвращает стратегию обработки ответа

        Args:
            response_type: Тип ответа от классификатора

        Returns:
            str: Стратегия обработки ('continue', 'change_topic', 'apologize', 'escalate')
        """
        strategies = {
            self.DIRECT_ANSWER: 'continue',      # Продолжаем обычный диалог
            self.DONT_KNOW: 'change_topic',       # Меняем вопрос на другой
            self.FRUSTRATION: 'apologize',        # Извиняемся и меняем тактику
            self.CLARIFICATION: 'answer',         # Отвечаем на вопрос пользователя
            self.IRRELEVANT: 'redirect',         # Перенаправляем к теме
            self.REFUSAL: 'escalate'             # Эскалируем оператору
        }

        return strategies.get(response_type, 'continue')
