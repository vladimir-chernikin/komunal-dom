#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FilterDetectionService - микросервис определения фильтров через LLM

После неудачной идентификации услуги анализирует историю диалога
и определяет фильтры для точного поиска:
- incident_type: Инцидент или Запрос
- location_type: Индивидуальное или Общедомовое
- category: категория проблемы
- object_description: описание объекта

ИСПРАВЛЕНО: Использует AIAgentService для всех вызовов LLM
"""

import logging
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FilterDetectionService:
    """Микросервис определения фильтров через LLM"""

    def __init__(self, ai_agent_service=None):
        """
        Инициализация сервиса

        Args:
            ai_agent_service: Экземпляр AIAgentService для вызов LLM
        """
        self.ai_agent = ai_agent_service
        self.is_available = ai_agent_service is not None

        logger.info(f"FilterDetectionService инициализирован (доступен: {self.is_available})")

    def _create_filter_detection_prompt(self, message_text: str, dialog_history: List[Dict]) -> str:
        """
        Создание промпта для определения фильтров

        Returns:
            str: Промпт для YandexGPT
        """
        # Формируем историю диалога для контекста
        history_text = ""
        if dialog_history:
            for msg in dialog_history[-5:]:  # Последние 5 сообщений
                role = "Пользователь" if msg.get('role') == 'user' else "Бот"
                history_text += f"{role}: {msg.get('text', '')}\n"

        prompt = f"""Ты - опытный диспетчер управляющей компании. Проанализируй обращение и определи фильтры для поиска услуги.

История диалога:
{history_text}

Текущее сообщение: "{message_text}"

ВАЖНО: Если в истории есть предыдущие сообщения пользователя, ОБЪЕДИ их с текущим для понимания контекста!
Например, если пользователь сказал "у меня течет", а потом "в ванной" - рассматривай как "у меня течет в ванной".

Определи и верни JSON в формате:
{{
    "incident_type": "Инцидент" или "Запрос",
    "location_type": "Индивидуальное" или "Общедомовое",
    "category": "Водоснабжение" или "Отопление" или "Электричество" или "Санитария" или "Конструктив" или "Лифты" или "Озеленение" или "Ремонт МАФ и покрытий",
    "object_description": "МАКСИМУМ 3 СЛОВА - объект+действие+место (пример: 'течь труба ванная', 'слабый напор кран')",
    "confidence": 0.0-1.0,
    "reason": "обоснование выбора"
}}

Правила:
- incident_type: "Инцидент" - если что-то сломалось/течет/не работает, "Запрос" - если нужна информация/услуга
- location_type: "Индивидуальное" - если в квартире/ванной/кухне/балконе, "Общедомовое" - если подъезд/лифт/подвал/крыша/двор
- category: выбери наиболее подходящую категорию из списка
- object_description: ТОЛЬКО 2-3 КЛЮЧЕВЫХ СЛОВА - что случилось+где (пример: 'прорыв трубы', 'течь ванная', 'засор кухня', 'слабый напор'). НЕ пиши 'не указано' или длинные фразы!
- confidence: от 0.5 до 1.0, где 1.0 = полная уверенность

Верни только JSON, без другого текста.

JSON:"""

        return prompt

    def _parse_llm_response(self, response_text: str) -> Dict:
        """Парсинг JSON ответа от LLM"""
        try:
            if not response_text:
                return {}

            # Ищем JSON в ответе
            json_match = response_text.find('{')
            if json_match != -1:
                json_str = response_text[json_match:]
                # Ищем закрывающую скобку
                last_brace = json_str.rfind('}')
                if last_brace != -1:
                    json_str = json_str[:last_brace + 1]
                    return json.loads(json_str)

            return json.loads(response_text)

        except json.JSONDecodeError as e:
            logger.error(f"FilterDetectionService: Ошибка парсинга JSON: {e}")
            logger.error(f"FilterDetectionService: Ответ был: {response_text}")
            return {}
        except Exception as e:
            logger.error(f"FilterDetectionService: Ошибка обработки ответа: {e}")
            return {}

    async def detect_filters(self, message_text: str, dialog_history: List[Dict] = None) -> Dict:
        """
        Определяет фильтры на основе истории диалога через LLM

        ИСПРАВЛЕНО: Использует AIAgentService вместо прямых запросов к API

        Args:
            message_text: Текущее сообщение пользователя
            dialog_history: История диалога

        Returns:
            Dict: Результат с определенными фильтрами
                {
                    'status': 'success' | 'error',
                    'filters': {
                        'incident_type': str,
                        'location_type': str,
                        'category': str,
                        'object_description': str
                    },
                    'confidence': float,
                    'reason': str
                }
        """
        try:
            logger.info(f"FilterDetectionService: Анализ фильтров для '{message_text[:50]}...' (история: {len(dialog_history or [])} сообщений)")

            if not self.is_available or not self.ai_agent:
                logger.warning("FilterDetectionService: недоступен (нет AIAgentService)")
                return {
                    'status': 'error',
                    'error': 'Service unavailable'
                }

            # Создаем промпт
            prompt = self._create_filter_detection_prompt(message_text, dialog_history or [])
            logger.info(f"FilterDetectionService: отправляем промпт через AIAgentService (длина: {len(prompt)} символов)")

            # ИСПРАВЛЕНО: Используем AIAgentService._call_yandex_gpt вместо прямого вызова API
            response, usage_info = await self.ai_agent._call_yandex_gpt(prompt)

            if not response:
                logger.warning("FilterDetectionService: не получили ответ от LLM через AIAgentService")
                return {
                    'status': 'error',
                    'error': 'No response from LLM'
                }

            # Парсим ответ
            parsed = self._parse_llm_response(response)

            if not parsed:
                logger.warning(f"FilterDetectionService: не удалось распарсить ответ: {response}")
                return {
                    'status': 'error',
                    'error': 'Failed to parse LLM response'
                }

            filters = {
                'incident_type': parsed.get('incident_type', ''),
                'location_type': parsed.get('location_type', ''),
                'category': parsed.get('category', ''),
                'object_description': parsed.get('object_description', '')
            }

            confidence = parsed.get('confidence', 0.0)
            reason = parsed.get('reason', '')

            logger.info(
                f"FilterDetectionService: определены фильтры: "
                f"incident_type={filters['incident_type']}, "
                f"location_type={filters['location_type']}, "
                f"category={filters['category']}, "
                f"confidence={confidence}"
            )

            return {
                'status': 'success',
                'filters': filters,
                'confidence': confidence,
                'reason': reason,
                'usage_info': usage_info
            }

        except Exception as e:
            logger.error(f"FilterDetectionService: Ошибка: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }

    async def rank_candidates_by_relevance(
        self,
        message_text: str,
        candidates: List[Dict],
        dialog_history: List[Dict] = None
    ) -> Dict:
        """
        Ранжирует кандидатов по релевантности через LLM

        ИЗБАВЛЯЕТ от хардкода keywords! Использует LLM для семантического сравнения.

        Args:
            message_text: Текущее сообщение пользователя
            candidates: Список кандидатов с атрибутами
                [{
                    'service_id': int,
                    'service_name': str,
                    'scenario_name': str,
                    'category': str,
                    'location_type': str,
                    'incident_type': str
                }, ...]
            dialog_history: История диалога

        Returns:
            Dict: {
                'status': 'success' | 'error',
                'recommended_id': int | None,  # ID наиболее подходящего кандидата
                'confidence': float,
                'reason': str,
                'ranking': [{service_id, service_name, score}]  # Все кандидаты с score
            }
        """
        try:
            if not self.is_available or not self.ai_agent:
                logger.warning("FilterDetectionService: недоступен для ранжирования")
                return {
                    'status': 'error',
                    'error': 'Service unavailable'
                }

            # Формируем контекст из истории
            context_text = message_text
            if dialog_history:
                user_msgs = [m.get('text', '') for m in dialog_history[-3:] if m.get('role') == 'user']
                if user_msgs:
                    context_text = ' '.join(user_msgs) + ' ' + message_text

            logger.info(f"FilterDetectionService: ранжирую {len(candidates)} кандидатов по контексту '{context_text[:80]}...'")

            # Формируем список кандидатов для LLM
            candidates_list = ""
            for i, c in enumerate(candidates, 1):
                name = c.get('service_name', c.get('scenario_name', 'Unknown'))
                cat = c.get('category', '')
                loc = c.get('location_type', '')
                candidates_list += f"{i}. ID:{c.get('service_id')} | {name} | Категория:{cat} | Локация:{loc}\n"

            # Создаем промпт для ранжирования
            prompt = f"""Ты - опытный диспетчер управляющей компании. Проанализируй обращение и выбери наиболее подходящую услугу.

КОНТЕКСТ ОБРАЩЕНИЯ:
"{context_text}"

ДОСТУПНЫЕ УСЛУГИ:
{candidates_list}

ЗАДАЧА: Выбери ТОЛЬКО ОДНУ наиболее подходящую услугу из списка выше.

Верни JSON в формате:
{{
    "recommended_id": 123,
    "confidence": 0.8,
    "reason": "почему выбрана эта услуга"
}}

Правила выбора:
- Анализируй что произошло (течет, сломалось, забито и т.д.)
- Учитывай место (квартира, подъезд, ванная, кухня)
- Сравни с названиями услуг
- Если есть несколько похожих - выбери наиболее точную
- confidence: от 0.5 до 1.0

Верни только JSON, без другого текста.

JSON:"""

            logger.info(f"FilterDetectionService: отправляем промпт ранжирования (длина: {len(prompt)} символов)")

            response, usage_info = await self.ai_agent._call_yandex_gpt(prompt)

            if not response:
                logger.warning("FilterDetectionService: не получили ответ при ранжировании")
                return {
                    'status': 'error',
                    'error': 'No response from LLM'
                }

            parsed = self._parse_llm_response(response)

            if not parsed:
                logger.warning(f"FilterDetectionService: не удалось распарсить ответ ранжирования: {response}")
                return {
                    'status': 'error',
                    'error': 'Failed to parse LLM response'
                }

            recommended_id = parsed.get('recommended_id')
            confidence = parsed.get('confidence', 0.0)
            reason = parsed.get('reason', '')

            # Проверяем что recommended_id есть в кандидатах
            valid_ids = [c.get('service_id') for c in candidates]
            if recommended_id not in valid_ids:
                logger.warning(f"FilterDetectionService: LLM вернул невалидный ID {recommended_id}, валидные: {valid_ids}")
                return {
                    'status': 'error',
                    'error': f'Invalid recommended_id: {recommended_id}'
                }

            logger.info(f"FilterDetectionService: рекомендован service_id={recommended_id}, confidence={confidence}, reason={reason}")

            return {
                'status': 'success',
                'recommended_id': recommended_id,
                'confidence': confidence,
                'reason': reason,
                'usage_info': usage_info
            }

        except Exception as e:
            logger.error(f"FilterDetectionService: Ошибка ранжирования: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
