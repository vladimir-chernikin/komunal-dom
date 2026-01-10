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

    def _create_filter_detection_prompt(self, message_text: str, dialog_history: List[Dict], txtPrb: str = None) -> str:
        """
        Создание оптимизированного промпта для определения фильтров

        ИСПРАВЛЕНО (2026-01-03): Оптимизация токенов (1082 → ~700)
        ИСПРАВЛЕНО (2026-01-10): Добавлен параметр txtPrb для анализа накопленного описания проблемы

        Args:
            message_text: Текущее сообщение пользователя
            dialog_history: История диалога
            txtPrb: Накопленное описание проблемы (КРИТИЧЕСКИ ВАЖНО!)

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

        # ИСПРАВЛЕНО (2026-01-06): Категории загружаются из БД (НЕ хардкод!)
        # Формируем список категорий для промпта
        categories_str = ", ".join([f'"{cat}"' for cat in self.categories_list])

        # ИСПРАВЛЕНО (2026-01-10): КРИТИЧЕСКИ ВАЖНО! Используем txtPrb вместо message_text
        # txtPrb содержит накопленное описание проблемы из всей истории диалога
        problem_description = txtPrb if txtPrb else message_text

        # ИСПРАВЛЕНО (2026-01-03): Оптимизированный промпт
        # ИСПРАВЛЕНО (2026-01-10): Усилены правила для incident_type и category
        # ИСПРАВЛЕНО (2026-01-10): Используем problem_description (txtPrb) вместо message_text
        prompt = f"""Анализируй обращение и верни JSON фильтров.

История (последние 3 сообщения):
{history_text}

⛔⛔⛔ КРИТИЧЕСКИ ВАЖНО - АНАЛИЗИРУЙ ПОЛНОЕ ОПИСАНИЕ ПРОБЛЕМЫ! ⛔⛔⛔
Накопленное описание проблемы (txtPrb): "{problem_description}"
Текущее сообщение: "{message_text}"

ОБЯЗАТЕЛЬНО используй txtPrb для анализа - это ПОЛНЫЙ контекст проблемы из всей истории диалога!

ДОСТУПНЫЕ КАТЕГОРИИ УСЛУГ (из базы данных):
{categories_str}

ВЕРНИ JSON:
{{
  "incident_type": "Инцидент" или "Запрос",
  "location_type": "Индивидуальное" или "Общедомовое" или null,
  "category": категория услуги или null,
  "object_description": "краткое описание проблемы",
  "confidence": 0.5-1.0,
  "reason": "обоснование выбора (обязательное поле!)"
}}

🚨🚨🚨 СУПЕР КРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ JSON 🚨🚨🚨
⛔⛔⛔ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО возвращать НЕВЕРНЫЙ JSON! ⛔⛔⛔

1. Поле "category" ДОЛЖНО быть:
   - ✅ ОДНОЙ строкой: "Водоснабжение"
   - ✅ null
   - ❌ НЕ списком: "Канализация", "Водоснабжение" (ЭТО ОШИБКА!)
   - ❌ НЕ массивом: ["Водоснабжение", "Отопление"] (ЭТО ОШИБКА!)

2. Если НЕУВЕРЕН в категории → ВСЕГДА возвращай category=null!
   - Лучше вернуть null чем НЕВЕРНЫЙ JSON с двумя категориями!

🚨🚨🚨 КОНЕЦ СУПЕР КРИТИЧЕСКОГО ПРАВИЛА 🚨🚨🚨

КРИТИЧЕСКИЕ ПРАВИЛА (ИИ ДОЛЖЕН САМ АНАЛИЗИРОВАТЬ СМЫСЛ!):

1. incident_type (Инцидент или Запрос):

⛔ ЗАПРЕЩЕНО: Использовать списки слов или ключевые маркеры!
✅ ОБЯЗАТЕЛЬНО: Анализировать СМЫСЛ описания проблемы и определять последствия!

АЛГОРИТМ ОПРЕДЕЛЕНИЯ:

ШАГ 1: Проанализируй текущее описание проблемы (txtPrb из истории)
- Что именно произошло?
- Какова природа проблемы?
- Что является ПРИЧИНОЙ?

ШАГ 2: Определи ПОСЛЕДСТВИЯ если проблему НЕ решат:
- "Если [txtPrb] не решат, то произойдет: ..."
- Оцени негативные последствия

ШАГ 3: Классифицируй по последствиям:

⛔ "Инцидент" = ЕСТЬ негативные последствия:
- УГРОЗА здоровью/жизни/имуществу (затопление, замыкание, падение, травмирование)
- УЩЕРБ помещению (порча вещей, мебели, ремонта)
- БЛОКИРОВКА жизненно важных функций (нет воды, нет света, нет отопления, нет газа)
- Аварийное состояние (разрушение, поломка, прорыв, течь, засор)

✅ "Запрос" = НЕТ негативных последствий:
- Желание получить информацию (спросить, узнать, почему, когда, как)
- Желание получить услугу (установить, заменить, подключить, поставить, смонтировать)
- Консультация (объяснить, рассказать, уточнить, разъяснить)

⛔ КРИТИЧЕСКИ ВАЖНО:
- НЕ используй списки слов-маркеров!
- НЕ ищи конкретные слова в тексте!
- АНАЛИЗИРУЙ СМЫСЛ описания проблемы!
- ПРИМЕНЯЙ ДВУХЭТАПНЫЙ АНАЛИЗ: описание → последствия → классификация

ПРИМЕРЫ ДЛЯ "ТЕЧЕТ" (чтобы НЕ ошибаться):
- "течет" → Инцидент (есть угроза затопления!)
- "капает" → Инцидент (есть угроза затопления!)
- "прорвало" → Инцидент (аварийная ситуация!)
- "протекает" → Инцидент (ущерб имуществу!)

2. location_type (Индивидуальное или Общедомовое или null):
   АНАЛИЗИРУЙ МЕСТО из контекста:
   - "Индивидуальное" = проблема ВНУТРИ квартиры/помещения пользователя
   - "Общедомовое" = проблема ОБЩИХ зон (подъезд, крыша, подвал, фасад)
   - null = если место не указано или неочевидно

   ⛔ НЕ ДОПУСКАЙ Поспешных выводов:
   - Фраза "у меня" сама по себе НЕ означает "в квартире"
   - Если пользователь говорит "у меня прорвало трубу" но НЕ уточняет где именно → location_type=null
   - Определяй location_type ТОЛЬКО при ЯВНОМ указании места в тексте

3. category (категория из списка выше):

⛔ КРИТИЧЕСКИ ВАЖНО - ТОЛЬКО ОДНА категория или null!
⛔ ЗАПРЕЩЕНО: Возвращать несколько категорий через запятую!

   - Используй СМЫСЛОВОЙ анализ контекста проблемы
   - УКАЗЫВАЙ категорию ТОЛЬКО при ЯВНОМ указании в тексте

   ⛔ НЕ ДОПУСКАЙ Поспешных выводов:
   - Слово "труба" само по себе НЕ означает "Водоснабжение" (трубы бывают для воды, отопления, канализации, газа)
   - Если пользователь НЕ указал что именно в трубе/какая проблема → category=null
   - Определяй category ТОЛЬКО при ЯВНОМ указании типа системы/жидкости/объекта

   🎯 АЛГОРИТМ ОПРЕДЕЛЕНИЯ CATEGORY С ВЕРОЯТНОСТЬЮ:
   ШАГ 1: Проанализируй описание проблемы (txtPrb)
   ШАГ 2: Для КАЖДОЙ категории из списка "ДОСТУПНЫЕ КАТЕГОРИИ" оцени вероятность 0-100%
   ШАГ 3: Если МАКСИМАЛЬНАЯ вероятность >= 80% → верни ЭТУ ОДНУ категорию (строкой!)
   ШАГ 4: Если МАКСИМАЛЬНАЯ вероятность < 80% → верни category=null

   ⛔ КРИТИЧЕСКИ ВАЖНО: Поле category должно быть строкой (одна категория) или null, НЕ списком!

   ПРИМЕРЫ ПРАВИЛЬНОГО ОПРЕДЕЛЕНИЯ:

   ПРИМЕР 1:
   Категории: "Водоснабжение", "Отопление", "Канализация"
   Текст: "течет из крана"
   → Водоснабжение: 85%, Отопление: 10%, Канализация: 5%
   → Макс: 85% >= 80% → category="Водоснабжение" (одна строка!)

   ПРИМЕР 2:
   Категории: "Водоснабжение", "Отопление", "Канализация"
   Текст: "прорвало трубу"
   → Водоснабжение: 40%, Отопление: 35%, Канализация: 25%
   → Макс: 40% < 80% → category=null (неуверенно!)

   ПРИМЕР 3 (анализ контекста "течет в зале"):
   Категории: "Водоснабжение", "Отопление", "Канализация", "Конструктив"
   Текст: "течет в зале"
   АНАЛИЗ:
   - В зале НЕТ кранов → НЕ Водоснабжение
   - В зале МОГУТ быть батареи → Отопление: 50%
   - В зале МОГУТ быть трубы отопления → Отопление: 30%
   - В зале МОЖЕТ протекать крыша → Конструктив: 20%
   → Макс: 50% < 80% → category=null (нужно уточнить: батарея? труба? крыша?)

   ПРИМЕР 4:
   Категории: "Водоснабжение", "Отопление", "Канализация"
   Текст: "течет батарея"
   → Отопление: 95%, Водоснабжение: 5%
   → Макс: 95% >= 80% → category="Отопление" (одна строка!)

   ПРИМЕР 5:
   Категории: "Водоснабжение", "Отопление", "Канализация"
   Текст: "течет из трубы"
   → Водоснабжение: 35%, Отопление: 35%, Канализация: 30%
   → Макс: 35% < 80% → category=null (трубы бывают разные!)

4. object_description:
   - Краткое описание проблемы: что случилось, где, какой объект
   - Максимальная длина: 5 слов

5. confidence:
   - 0.5-0.7 = низкая уверенность
   - 0.7-0.9 = средняя уверенность
   - 0.9-1.0 = высокая уверенность

6. reason:
   - Обоснуй почему выбраны именно эти фильтры

⛔ КРИТИЧЕСКИ ВАЖНО:
- НЕ используй хардкод помещений или категорий
- НЕ используй списки синонимов или примеров
- АНАЛИЗИРУЙ СМЫСЛ описания проблемы самостоятельно

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

    async def detect_filters(self, message_text: str, dialog_history: List[Dict] = None, txtPrb: str = None, session_id: str = None, message_id: int = None) -> Dict:
        """
        Определяет фильтры на основе истории диалога через LLM

        ИСПРАВЛЕНО: Использует AIAgentService вместо прямых запросов к API
        ИСПРАВЛЕНО (2026-01-10): Добавлен параметр txtPrb для анализа накопленного описания проблемы

        Args:
            message_text: Текущее сообщение пользователя
            dialog_history: История диалога
            txtPrb: Накопленное описание проблемы (ProblemAccumulationService) - КРИТИЧЕСКИ ВАЖНО!

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
        logger.info("[SEARCH] FilterDetectionService ВХОДЯЩИЕ ПАРАМЕТРЫ:")
        logger.info(f"  [NOTE] message_text: '{message_text[:80]}'")
        logger.info(f"  [LIST] dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")

        try:
            logger.info(f"FilterDetectionService: Анализ фильтров для '{message_text[:50]}...' (история: {len(dialog_history or [])} сообщений)")

            if not self.is_available or not self.ai_agent:
                logger.warning("FilterDetectionService: недоступен (нет AIAgentService)")
                return {
                    'status': 'error',
                    'error': 'Service unavailable'
                }

            # Создаем промпт
            # ИСПРАВЛЕНО (2026-01-10): Передаем txtPrb для анализа накопленного описания проблемы
            prompt = self._create_filter_detection_prompt(message_text, dialog_history or [], txtPrb)

            # ИСПРАВЛЕНО (2025-12-28): Логируем промт
            logger.info(f"🤖 FilterDetection PROMPT:")
            logger.info(f"{'=' * 80}")
            logger.info(f"{prompt[:500]}...")
            logger.info(f"{'=' * 80} (длина: {len(prompt)} символов)")

            logger.info(f"FilterDetectionService: отправляем промпт через AIAgentService (длина: {len(prompt)} символов)")

            # ИСПРАВЛЕНО (2025-12-28): Используем универсальный метод call_llm
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',  # Можно менять на 'gigachat'
                model='lite',          # Или 'pro', 'GigaChat', 'GigaChat-2', etc.
                session_id=session_id,  # ИСПРАВЛЕНО (2026-01-06)
                message_id=message_id   # ИСПРАВЛЕНО (2026-01-06)
            )

            # ИСПРАВЛЕНО (2025-12-28): Логируем ответ
            logger.info(f"🤖 FilterDetection ОТВЕТ LLM:")
            logger.info(f"  [NOTE] Raw response: '{response[:300]}'")
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

            # ИСПРАВЛЕНО (2026-01-10): Добавлено логирование reason для отладки
            logger.info(
                f"FilterDetectionService: определены фильтры: "
                f"incident_type={filters['incident_type']}, "
                f"location_type={filters['location_type']}, "
                f"category={filters['category']}, "
                f"confidence={confidence}"
            )
            logger.info(f"FilterDetectionService: REASON (обоснование): {reason}")

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
        dialog_history: List[Dict] = None,
        session_id: str = None
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
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id для логирования
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                session_id=session_id  # ИСПРАВЛЕНО (2026-01-06)
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
