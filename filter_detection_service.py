#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FilterDetectionService - микросервис определения фильтров через LLM

После неудачной идентификации услуги анализирует историю диалога
и определяет фильтры для точного поиска:
- incident_type: Инцидент или Запрос
- location_type: Индивидуальное или Общедомовое
- category: категория проблемы

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
                    # ИСПРАВЛЕНО (2026-01-16): Загружаем уникальные категории через JOIN с ref_categories
                    cursor.execute("""
                        SELECT DISTINCT rc.category_name
                        FROM services_catalog sc
                        JOIN ref_categories rc ON sc.category_id = rc.category_id
                        WHERE rc.category_name IS NOT NULL AND rc.category_name != ''
                        ORDER BY rc.category_name
                    """)
                    self.categories_list = [row[0] for row in cursor.fetchall()]

                    # ИСПРАВЛЕНО (2026-01-16): Загружаем примеры объектов через JOIN с ref_* таблицами
                    cursor.execute("""
                        SELECT sc.scenario_name,
                               COALESCE(rc.category_name, '') as category,
                               COALESCE(rst.type_name, '') as incident_type
                        FROM services_catalog sc
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        LEFT JOIN ref_service_types rst ON sc.type_id = rst.type_id
                        WHERE sc.is_active = TRUE
                        ORDER BY sc.service_id
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

        # ИСПРАВЛЕНО (2026-01-20): Новый алгоритмический промпт
        prompt = f"""## Роль
Ты — строгий алгоритмический классификатор. Выполняй ТОЛЬКО алгоритм. НЕ придумывай факты. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{problem_description}"
CATEGORIES = [{categories_str}]

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. incident_type (ИЕРАРХИЯ УГРОЗ)
**ПРИМЕР "течёт труба": угроза имуществу(вода) → Инцидент(0.8)**

incident_type = null
incident_confidence = "0.5"

# 2.1 Угроза жизни? (потоп/обрушение)
если ДА: incident_type="Инцидент"; incident_confidence="1.0"
reasoning_txt += " | 2.1: [" + последствия + "] → " + (ДА/НЕТ)

# 2.2 Угроза здоровью? (плесень/травма)
если incident_confidence=="0.5" и ДА: incident_type="Инцидент"; incident_confidence="0.9"
reasoning_txt += " | 2.2: [" + последствия + "] → " + (ДА/НЕТ)

# 2.3 Угроза имуществу? (повреждение квартиры)
если incident_confidence=="0.5" и ДА: incident_type="Инцидент"; incident_confidence="0.8"
reasoning_txt += " | 2.3: [" + последствия + "] → " + (ДА/НЕТ)

# 2.4 Запрос без срочности?
если incident_confidence=="0.5" и ДА: incident_type="Запрос"; incident_confidence="0.7"
reasoning_txt += " | 2.4: " + (ДА/НЕТ)

reasoning_txt += " | incident_type=" + incident_type + "(" + incident_confidence + ")"

### Шаг3. location_type
SCOPE = "внутри"|"вне"|"null"
location_type = "Индивидуальное" если SCOPE=="внутри" else "Общедомовое" если "вне" else null
location_confidence = "1.0" если не null else "0.5"
reasoning_txt += " | Шаг3: " + PLACE + "=[" + SCOPE + "] → location_type=" + location_type + "(" + location_confidence + ")"

### Шаг4. Category (ВСЕ CATEGORIES! sum релев=1.0, impossible=0.0)

M_EVENT = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные: распредели sum=1.0
M_EVENT["Водоснабжение"]=0.4; M_EVENT["Канализация"]=0.3; M_EVENT["Отопление"]=0.2; M_EVENT["Газоснабжение"]=0.1  # пример adjust
reasoning_txt += " | 4.1: M_EVENT=" + str(M_EVENT) + " (sum релев=1.0)"

M_PLACE = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные в PLACE sum=1.0 (равно если неоднозначно)
M_PLACE["Водоснабжение"]=0.33; M_PLACE["Канализация"]=0.33; M_PLACE["Отопление"]=0.34
reasoning_txt += " | 4.2: M_PLACE=" + str(M_PLACE) + " (sum=1.0)"

M_OBJ = {{cat: 0.0 for cat in CATEGORIES}}
M_OBJ["Водоснабжение"]=0.33; M_OBJ["Канализация"]=0.33; M_OBJ["Отопление"]=0.34
reasoning_txt += " | 4.3: M_OBJ=" + str(M_OBJ) + " (sum=1.0)"

M_CANDIDATE = {{}}
for cat in CATEGORIES:
    M_CANDIDATE[cat] = round(M_OBJ[cat] * M_EVENT[cat] * M_PLACE[cat], 3)
reasoning_txt += " | 4.4: M_CANDIDATE=" + str(M_CANDIDATE)

Z1_cat = max(M_CANDIDATE, key=M_CANDIDATE.get)
Z1 = M_CANDIDATE[Z1_cat]
total = sum(M_CANDIDATE.values())
ostatok = total - Z1
if Z1 > ostatok * 0.7:
    category = Z1_cat
    category_confidence = str(round(Z1, 1))
else:
    category = null
    category_confidence = "0.5"
reasoning_txt += " | 4.5: Z1=" + Z1_cat + "(" + str(Z1) + "), total=" + str(total) + ", остаток=" + str(ostatok) + ", " + str(Z1) + ">" + str(ostatok*0.7) + "=" + (ДА/НЕТ) + " → category=" + str(category) + "(" + category_confidence + ")"

### Шаг5. ПРОВЕРКА И JSON
**ПРОВЕРЬ: category из 4.5? incident из 2?**
{{
  "incident_type": """ + incident_type + """",
  "incident_confidence": """ + incident_confidence + """",
  "location_type": """ + location_type + """",
  "location_confidence": """ + location_confidence + """",
  "category": """ + category + """",
  "category_confidence": """ + category_confidence + """",
  "reasoning": """ + reasoning_txt + """
}}"""

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
        ИСПРАВЛЕНО (2026-01-15): Убран object_description (используется txtPrb)

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
                        'category': str
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
                'category': parsed.get('category', '')
            }

            # ИСПРАВЛЕНО (2026-01-15): Извлекаем отдельные confidence для каждого поля
            incident_confidence = parsed.get('incident_confidence', 0.5)
            location_confidence = parsed.get('location_confidence', 0.5)
            category_confidence = parsed.get('category_confidence', 0.5)
            reasoning = parsed.get('reasoning', parsed.get('reason', ''))

            # Общая уверенность = минимум из трех (консервативная оценка)
            confidence = min(incident_confidence, location_confidence, category_confidence)

            # ИСПРАВЛЕНО (2026-01-15): Добавлено логирование confidence для отладки
            logger.info(
                f"FilterDetectionService: определены фильтры: "
                f"incident_type={filters['incident_type']} (conf={incident_confidence}), "
                f"location_type={filters['location_type']} (conf={location_confidence}), "
                f"category={filters['category']} (conf={category_confidence}), "
                f"overall_confidence={confidence}"
            )
            logger.info(f"FilterDetectionService: REASONING (обоснование): {reasoning}")

            # ДОБАВЛЕНО: Сохраняем промт и ответ для трассировки
            return {
                'status': 'success',
                'filters': filters,
                'confidence': confidence,
                'reason': reasoning,  # ИСПРАВЛЕНО (2026-01-15): было reason, стало reasoning
                'usage_info': usage_info,
                'prompt': prompt,  # ДОБАВЛЕНО: промт для трассировки
                'llm_response': response,  # ДОБАВЛЕНО: ответ LLM для трассировки
                'parsed_response': parsed,  # ДОБАВЛЕНО: распаршенный ответ
                'incident_confidence': incident_confidence,  # ИСПРАВЛЕНО (2026-01-15)
                'location_confidence': location_confidence,  # ИСПРАВЛЕНО (2026-01-15)
                'category_confidence': category_confidence  # ИСПРАВЛЕНО (2026-01-15)
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
