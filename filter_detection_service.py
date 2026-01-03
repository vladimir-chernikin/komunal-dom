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
ИСПРАВЛЕНО (2025-12-25): Загружает категории и объекты из БД вместо хардкода
"""

import logging
import json
from typing import Dict, List, Optional
from django.db import connection
from asgiref.sync import sync_to_async

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

        # ИСПРАВЛЕНО (2025-12-25): Загружаем категории и объекты из БД
        self.categories_list = []
        self.objects_examples = []
        self._load_reference_data_from_db()

        logger.info(f"FilterDetectionService инициализирован (доступен: {self.is_available})")

    def _load_reference_data_from_db(self):
        """Загружает справочные данные из БД для промпта"""
        try:
            # ИСПРАВЛЕНО (2025-12-28): Прямой SQL запрос без Django ORM
            # Это безопаснее для инициализации в async контексте
            import psycopg2
            from django.conf import settings

            db_settings = settings.DATABASES['default']
            conn = psycopg2.connect(
                host=db_settings['HOST'],
                database=db_settings['NAME'],
                user=db_settings['USER'],
                password=db_settings['PASSWORD'],
                port=db_settings.get('PORT', 5432)
            )

            try:
                with conn.cursor() as cursor:
                    # Загружаем уникальные категории
                    cursor.execute("""
                        SELECT DISTINCT category
                        FROM services_catalog
                        WHERE category IS NOT NULL AND category != ''
                        ORDER BY category
                    """)
                    self.categories_list = [row[0] for row in cursor.fetchall()]

                    # Загружаем примеры объектов (scenario_name)
                    cursor.execute("""
                        SELECT scenario_name, category, incident_type
                        FROM services_catalog
                        WHERE is_active = TRUE
                        ORDER BY service_id
                        LIMIT 30
                    """)
                    self.objects_examples = [
                        {
                            'name': row[0],
                            'category': row[1],
                            'incident': row[2]
                        }
                        for row in cursor.fetchall()
                    ]
            finally:
                conn.close()

            logger.info(
                f"FilterDetectionService: загружено {len(self.categories_list)} категорий, "
                f"{len(self.objects_examples)} примеров объектов"
            )

        except Exception as e:
            logger.error(f"Ошибка загрузки справочных данных: {e}")
            self.categories_list = []
            self.objects_examples = []

    def _create_filter_detection_prompt(self, message_text: str, dialog_history: List[Dict]) -> str:
        """
        Создание оптимизированного промпта для определения фильтров

        ИСПРАВЛЕНО (2026-01-03): Оптимизация токенов (1082 → ~700)

        Returns:
            str: Промпт для YandexGPT
        """
        # ИСПРАВЛЕНО (2026-01-03): Сокращаем историю с 5 до 3 сообщений
        history_text = ""
        if dialog_history:
            for msg in dialog_history[-3:]:
                role = "П" if msg.get('role') == 'user' else "Б"
                text = msg.get('text', '')[:50]  # Сокращаем сообщения
                history_text += f"{role}: {text}...\n"

        # Категории (сокращаем до 10 самых частых)
        categories_str = ", ".join([f'"{cat}"' for cat in self.categories_list[:10]])

        # ИСПРАВЛЕНО (2026-01-03): Оптимизированные примеры объектов
        # Берем только 3 категории по 2 примера (вместо 5x3)
        objects_examples_text = ""
        if self.objects_examples:
            from collections import defaultdict
            by_category = defaultdict(list)
            for obj in self.objects_examples[:10]:  # 10 вместо 15
                by_category[obj['category']].append(obj['name'])

            for cat, names in sorted(by_category.items())[:3]:  # 3 вместо 5
                objects_examples_text += f"- {cat}: {', '.join(names[:2])}\n"  # 2 вместо 3

        # ИСПРАВЛЕНО (2026-01-03): Оптимизированный промпт
        prompt = f"""Анализируй обращение и верни JSON фильтров.

История (последние 3 сообщения):
{history_text}

Текущее: "{message_text}"

ПРАВИЛА ОБЪЕДИНЕНИЯ: Если пользователь сказал "течет", потом "в ванной" = "течет в ванной".

КАТЕГОРИИ: {categories_str}

ПРИМЕРЫ ОБЪЕКТОВ:
{objects_examples_text}

ВЕРНИ JSON:
{{
  "incident_type": "Инцидент" или "Запрос",
  "location_type": "Индивидуальное" или "Общедомовое" или null,
  "category": категория или null,
  "object_description": "объект действие место (макс 3 слова)",
  "confidence": 0.5-1.0,
  "reason": "обоснование"
}}

КРИТИЧЕСКИ:
1. ТЕЧЕТ/ПРОРЫВ/ЗАТОПЛЕНИЕ = "Инцидент", confidence: 1.0
2. "Инцидент" = сломалось/течет/не работает/засор
3. "Запрос" = ХОЧЕТ ИНФОРМАЦИЮ (спросить/узнать/почему)
4. location_type: ЯВНО "в квартире/ванной/кухне" = "Индивидуальное", "подъезд/крыша" = "Общедомовое", иначе null
5. category: УКАЗЫВАЙ только при 100% уверенности (батарея=Отопление), иначе null
6. НЕ указывай location и category если неочевидно!

Верни только JSON.

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
        # ИСПРАВЛЕНО (2025-12-28): Отладочные логи
        logger.info("🔍 FilterDetectionService ВХОДЯЩИЕ ПАРАМЕТРЫ:")
        logger.info(f"  📝 message_text: '{message_text[:80]}'")
        logger.info(f"  📋 dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")

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

            # ИСПРАВЛЕНО (2025-12-28): Логируем промт
            logger.info(f"🤖 FilterDetection PROMPT:")
            logger.info(f"{'=' * 80}")
            logger.info(f"{prompt[:500]}...")
            logger.info(f"{'=' * 80} (длина: {len(prompt)} символов)")

            logger.info(f"FilterDetectionService: отправляем промпт через AIAgentService (длина: {len(prompt)} символов)")

            # ИСПРАВЛЕНО (2025-12-28): Используем универсальный метод call_llm
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',  # Можно менять на 'gigachat'
                model='lite'            # Или 'pro', 'GigaChat', 'GigaChat-2', etc.
            )

            # ИСПРАВЛЕНО (2025-12-28): Логируем ответ
            logger.info(f"🤖 FilterDetection ОТВЕТ LLM:")
            logger.info(f"  📝 Raw response: '{response[:300]}'")
            logger.info(f"  💰 Usage: {usage_info}")

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

            # ДОБАВЛЕНО: Сохраняем промт и ответ для трассировки
            return {
                'status': 'success',
                'filters': filters,
                'confidence': confidence,
                'reason': reason,
                'usage_info': usage_info,
                'prompt': prompt,  # ДОБАВЛЕНО: промт для трассировки
                'llm_response': response,  # ДОБАВЛЕНО: ответ LLM для трассировки
                'parsed_response': parsed  # ДОБАВЛЕНО: распаршенный ответ
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
ВАЖНО: В поле recommended_id укажи ТОЛЬКО ID из списка выше (число после "ID:").

Верни JSON в формате:
{{
    "recommended_id": 25,
    "confidence": 0.8,
    "reason": "почему выбрана эта услуга"
}}

Правила выбора:
- Анализируй что произошло (течет, сломалось, забито и т.д.)
- Учитывай место (квартира, подъезд, ванная, кухня)
- Сравни с названиями услуг в списке
- Если есть несколько похожих - выбери наиболее точную
- confidence: от 0.5 до 1.0
- recommended_id: ТОЛЬКО число из колонки "ID:" в списке выше!

Верни только JSON, без другого текста.

JSON:"""

            logger.info(f"FilterDetectionService: отправляем промпт ранжирования (длина: {len(prompt)} символов)")

            # ИСПРАВЛЕНО (2025-12-28): Используем универсальный метод call_llm
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite'
            )

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
