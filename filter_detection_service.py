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

Определи и верни JSON в формате:
{{
    "incident_type": "Инцидент" или "Запрос",
    "location_type": "Индивидуальное" или "Общедомовое",
    "category": "Водоснабжение" или "Отопление" или "Электричество" или "Санитария" или "Конструктив" или "Лифты" или "Озеленение" или "Ремонт МАФ и покрытий",
    "object_description": "краткое описание объекта (труба, кран, батарея и т.д.)",
    "confidence": 0.0-1.0,
    "reason": "обоснование выбора"
}}

Правила:
- incident_type: "Инцидент" - если что-то сломалось/течет/не работает, "Запрос" - если нужна информация/услуга
- location_type: "Индивидуальное" - если в квартире/ванной/кухне/балконе, "Общедомовое" - если подъезд/лифт/подвал/крыша/двор
- category: выбери наиболее подходящую категорию из списка
- object_description: опиши конкретный объект (труба канализации, кран, батарея и т.д.)
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
