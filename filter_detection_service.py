#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FilterDetectionService - микросервис определения фильтров через LLM

ИСПРАВЛЕНО (2026-01-20): Разбит на 3 отдельных промпта:
- incident_type (Инцидент/Запрос)
- location_type (Индивидуальное/Общедомовое)
- category (категория проблемы)

ИЗМЕНЕНО (2026-03-22): category ПЕРЕВКЛЮЧЕН

Каждый промпт возвращает упрощенный JSON: {[filter], [confidence], [reasoning]}
Итоговый JSON собирается внутри Python кода.
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class FilterDetectionService:
    """Микросервис определения фильтров через LLM (разбит на 3 промпта)"""

    def __init__(self, ai_agent_service=None):
        """
        Инициализация сервиса

        Args:
            ai_agent_service: Экземпляр AIAgentService для вызов LLM
        """
        self.ai_agent = ai_agent_service
        self.is_available = ai_agent_service is not None

        # Загружаем категории из БД
        self.categories_list = []
        self.objects_examples = []
        self._load_reference_data_from_db()

        logger.info(f"FilterDetectionService инициализирован (доступен: {self.is_available})")

    def _load_reference_data_from_db(self):
        """
        Загружает справочные данные из БД для промпта

        ИЗМЕНЕНО (2026-03-22):
        - Добавлена загрузка категорий с полями: ID, name, llm_description, is_default
        - categories_list УДАЛЕН (рудимент)
        - Добавлено определение is_default_id
        """
        try:
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
                    # ИЗМЕНЕНО (2026-03-22): Загружаем категории с полными данными
                    cursor.execute("""
                        SELECT category_id, category_name, llm_description, is_default
                        FROM ref_categories
                        ORDER BY category_name
                    """)
                    self.categories_data = [
                        {
                            'id': row[0],
                            'name': row[1],
                            'description': row[2],
                            'is_default': row[3]
                        }
                        for row in cursor.fetchall()
                    ]

                    # ИЗМЕНЕНО (2026-03-22): Находим is_default_id
                    default_categories = [c for c in self.categories_data if c['is_default']]
                    self.is_default_id = default_categories[0]['id'] if default_categories else None

                    # Загружаем примеры объектов
                    # ИСПРАВЛЕНО (2026-03-25): Новая структура - текстовые поля вместо JOIN
                    cursor.execute("""
                        SELECT scenario_name,
                               category_name as category,
                               type_name as incident_type,
                               localization_name as localization
                        FROM services_catalog
                        WHERE is_active = TRUE
                        ORDER BY service_id
                        LIMIT 100
                    """)
                    self.objects_examples = [
                        {
                            'name': row[0],
                            'category': row[1],
                            'incident': row[2],
                            'localization': row[3]
                        }
                        for row in cursor.fetchall()
                    ]
            finally:
                conn.close()

            logger.info(
                f"FilterDetectionService: загружено {len(self.categories_data)} категорий, "
                f"is_default_id={self.is_default_id}, "
                f"{len(self.objects_examples)} примеров объектов"
            )

        except Exception as e:
            logger.error(f"Ошибка загрузки справочных данных: {e}")
            self.categories_data = []
            self.is_default_id = None
            self.objects_examples = []

    # ========================================================================
    # ПРОМПТ 1: incident_type (Инцидент/Запрос)
    # ========================================================================

    async def _create_incident_type_prompt(self, txtPrb: str) -> str:
        """
        Создание промпта для определения incident_type

        ИСПРАВЛЕНО (2026-02-05): Загружает промпт из БД вместо хардкода.
        ИСПРАВЛЕНО (2026-03-06): Убрано формирование examples (Ольга добавляла тупо).
        """
        # ИСПРАВЛЕНО (2026-02-05): Загружаем промпт из БД
        # ИСПРАВЛЕНО (2026-02-24): Исправлен fallback - теперь выполняется ТОЛЬКО если промпт не найден
        try:
            from llm_tester.models import PromptTemplate
            from asgiref.sync import sync_to_async

            @sync_to_async
            def get_db_template():
                return PromptTemplate.objects.filter(
                    slug='filter-incident-type',
                    is_active=True
                ).first()

            db_template = await get_db_template()

            if db_template:
                # Подставляем переменные в шаблон из БД
                prompt = db_template.template.format(txtPrb=txtPrb)

                logger.debug(f"[DB] Промпт filter-incident-type загружен из БД (ID: {db_template.id})")
                return prompt
            else:
                logger.error(f"[DB] Промпт 'filter-incident-type' не найден в БД!")
                # ИСПРАВЛЕНО (2026-02-24): Fallback ТОЛЬКО если не найден
                logger.warning("[FALLBACK] Используется fallback-промпт для incident_type")
                raise Exception(
                    f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-incident-type' не найден в БД!\n"
                    f"Создайте промпт в админке: /admin-uk/llm_tester/prompttemplate/\n"
                    f"Slug: 'filter-incident-type'\n"
                    f"Is Active: True"
                )
        except Exception as e:
            logger.error(f"[DB] Ошибка загрузки промпта из БД: {e}")
            raise Exception(
                f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-incident-type' не загружен!\n"
                f"Ошибка: {e}"
            )

    # ========================================================================
    # ПРОМПТ 2: location_type (Индивидуальное/Общедомовое)
    # ========================================================================

    async def _create_location_type_prompt(self, txtPrb: str) -> str:
        """
        Создание промпта для определения location_type

        ИСПРАВЛЕНО (2026-02-05): Загружает промпт из БД вместо хардкода.
        ИСПРАВЛЕНО (2026-03-06): Убрано формирование examples (Ольга добавляла тупо).
        """
        # ИСПРАВЛЕНО (2026-02-05): Загружаем промпт из БД
        try:
            from llm_tester.models import PromptTemplate
            from asgiref.sync import sync_to_async

            @sync_to_async
            def get_db_template():
                return PromptTemplate.objects.filter(
                    slug='filter-location-type',
                    is_active=True
                ).first()

            db_template = await get_db_template()

            if db_template:
                # Подставляем переменные в шаблон из БД
                prompt = db_template.template.format(txtPrb=txtPrb)

                logger.debug(f"[DB] Промпт filter-location-type загружен из БД (ID: {db_template.id})")
                return prompt
            else:
                logger.error(f"[DB] Промпт 'filter-location-type' не найден в БД!")
                raise Exception(
                    f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-location-type' не найден в БД!\n"
                    f"Создайте промпт в админке: /admin-uk/llm_tester/prompttemplate/\n"
                    f"Slug: 'filter-location-type'\n"
                    f"Is Active: True"
                )
        except Exception as e:
            logger.error(f"[DB] Ошибка загрузки промпта из БД: {e}")
            raise Exception(
                f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-location-type' не загружен!\n"
                f"Ошибка: {e}"
            )

    # ========================================================================
    # ПРОМПТ 3: category (категория проблемы)
    # ========================================================================

    async def _create_category_prompt(self, txtPrb: str) -> str:
        """
        Создание промпта для определения category

        ИСПРАВЛЕНО (2026-02-05): Загружает промпт из БД вместо хардкода.
        ИСПРАВЛЕНО (2026-03-07): Убрано формирование examples (Ольга добавляла тупо).
        ИЗМЕНЕНО (2026-03-22):
        - categories_str УДАЛЕН (рудимент)
        - categories_json формируется из БД (ID, name, llm_description, is_default=false)
        - is_default_id подставляется из БД
        - Используется .format() вместо replace
        """
        # ИЗМЕНЕНО (2026-03-22): Формируем JSON только с is_default=false
        categories_for_json = [
            {
                'id': cat['id'],
                'name': cat['name'],
                'description': cat['description']
            }
            for cat in self.categories_data
            if not cat['is_default']
        ]
        categories_json = json.dumps(categories_for_json, ensure_ascii=False, indent=2)

        # ИСПРАВЛЕНО (2026-02-05): Загружаем промпт из БД
        try:
            from llm_tester.models import PromptTemplate
            from asgiref.sync import sync_to_async

            @sync_to_async
            def get_db_template():
                return PromptTemplate.objects.filter(
                    slug='filter-category',
                    is_active=True
                ).first()

            db_template = await get_db_template()

            if db_template:
                # ИЗМЕНЕНО (2026-03-22): Подставляем переменные через .format()
                prompt = db_template.template.format(
                    txtPrb=txtPrb,
                    categories_json=categories_json,
                    is_default_id=self.is_default_id
                )

                logger.debug(f"[DB] Промпт filter-category загружен из БД (ID: {db_template.id})")
                logger.debug(f"[DB] categories_json: {len(categories_for_json)} категорий, is_default_id={self.is_default_id}")
                return prompt
            else:
                logger.error(f"[DB] Промпт 'filter-category' не найден в БД!")
                raise Exception(
                    f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-category' не найден в БД!\n"
                    f"Создайте промпт в админке: /admin-uk/llm_tester/prompttemplate/\n"
                    f"Slug: 'filter-category'\n"
                    f"Is Active: True"
                )
        except Exception as e:
            logger.error(f"[DB] Ошибка загрузки промпта из БД: {e}")
            raise Exception(
                f"❌ КРИТИЧЕСКАЯ ОШИБКА: Промпт 'filter-category' не загружен!\n"
                f"Ошибка: {e}"
            )

        # Fallback-промпт ОТКЛЮЧЕН (2026-02-18) - используем только боевой
        # logger.warning("[FALLBACK] Используется fallback-промпт для category")
        # prompt = f"""⚠️ ТЕХНИЧЕСКАЯ ОШИБКА: Промпт не найден в базе данных!
        # TXT_PRB = "{txtPrb}"
        # CATEGORIES = [{categories_str}]
        # ОПРЕДЕЛИ КАТЕГОРИЮ из списка выше.
        # Верни JSON: {{"category": "категория", "confidence": 0.7, "reasoning": "обоснование"}}"""
        # return prompt

    # ========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ========================================================================

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

    async def _call_llm_for_filter(
        self,
        prompt: str,
        filter_name: str,
        session_id: str = None,
        message_id: int = None
    ) -> Dict:
        """
        Выполняет LLM запрос для одного фильтра

        Returns:
            Dict: {
                'filter_name': str,
                'value': str,
                'confidence': float,
                'reasoning': str,
                'prompt': str,
                'response': str,
                'usage_info': Dict
            }
        """
        try:
            logger.info(f"🤖 FilterDetection [{filter_name}] PROMPT:")
            logger.info(f"{'=' * 80}")
            logger.info(f"{prompt[:500]}...")
            logger.info(f"{'=' * 80} (длина: {len(prompt)} символов)")

            # ИСПРАВЛЕНО (2026-03-07): Формируем уникальный service_name для каждого фильтра
            service_name = f"FilterDetectionService ({filter_name})"

            # Вызываем LLM
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider=None,  # Используем провайдер из env (DEFAULT_LLM_PROVIDER)
                model=None,  # Используем модель по умолчанию из .env
                session_id=session_id,
                message_id=message_id,
                service_name=service_name
            )

            logger.info(f"🤖 FilterDetection [{filter_name}] ОТВЕТ LLM:")
            logger.info(f"  [NOTE] Raw response: '{response[:300]}'")
            logger.info(f"  💰 Usage: {usage_info}")

            if not response:
                logger.warning(f"FilterDetectionService [{filter_name}]: не получили ответ от LLM")
                return {
                    'filter_name': filter_name,
                    'value': None,
                    'confidence': 0.5,
                    'reasoning': 'No response from LLM',
                    'prompt': prompt,
                    'response': '',
                    'usage_info': usage_info
                }

            # Парсим ответ
            parsed = self._parse_llm_response(response)

            if not parsed:
                logger.warning(f"FilterDetectionService [{filter_name}]: не удалось распарсить ответ")
                return {
                    'filter_name': filter_name,
                    'value': None,
                    'confidence': 0.5,
                    'reasoning': 'Failed to parse LLM response',
                    'prompt': prompt,
                    'response': response,
                    'usage_info': usage_info
                }

            # Извлекаем значения (разные поля для разных фильтров)
            if filter_name == 'incident_type':
                value = parsed.get('incident_type')
                confidence = float(parsed.get('confidence', 0.5))
            elif filter_name == 'location_type':
                value = parsed.get('location_type')
                confidence = float(parsed.get('confidence', 0.5))
            elif filter_name == 'category':
                value = parsed.get('category')
                confidence = float(parsed.get('confidence', 0.5))
                # ИСПРАВЛЕНИЕ (2026-02-13): Печатаем в stderr для отладки
                print(f"[DEBUG] FilterDetectionService[{filter_name}]: value={value}, confidence={confidence}, parsed={parsed}")
            else:
                value = None
                confidence = 0.5

            reasoning = parsed.get('reasoning', '')

            return {
                'filter_name': filter_name,
                'value': value,
                'confidence': confidence,
                'reasoning': reasoning,
                'prompt': prompt,
                'response': response,
                'usage_info': usage_info,
                'parsed_response': parsed
            }

        except Exception as e:
            logger.error(f"FilterDetectionService [{filter_name}]: Ошибка: {e}")
            return {
                'filter_name': filter_name,
                'value': None,
                'confidence': 0.5,
                'reasoning': f'Error: {str(e)}',
                'prompt': prompt,
                'response': '',
                'usage_info': {}
            }

    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: detect_filters (объединяет 3 промпта)
    # ========================================================================

    async def detect_filters(
        self,
        message_text: str,
        dialog_history: List[Dict] = None,
        txtPrb: str = None,
        session_id: str = None,
        message_id: int = None
    ) -> Dict:
        """
        Определяет все фильтры через 3 отдельных промпта

        ИСПРАВЛЕНО (2026-01-20): Разбит на 3 промпта (incident_type, location_type, category)
        ИСПРАВЛЕНО (2026-01-27): Category ОТКЛЮЧЕН, используется только 2 промпта
        ИСПРАВЛЕНО (2026-01-30): Category ПЕРЕВКЛЮЧЕН, используется 3 промпта

        Args:
            message_text: Текущее сообщение пользователя
            dialog_history: История диалога
            txtPrb: Накопленное описание проблемы (ProblemAccumulationService) - КРИТИЧЕСКИ ВАЖНО!
            session_id: ID сессии для логирования
            message_id: ID сообщения для логирования

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
                    'reason': str,
                    'details': {
                        'incident_type': {...},
                        'location_type': {...},
                        'category': {...}
                    }
                }
        """
        logger.info("[SEARCH] FilterDetectionService ВХОДЯЩИЕ ПАРАМЕТРЫ:")
        logger.info(f"  [NOTE] message_text: '{message_text[:80]}'")
        logger.info(f"  [LIST] dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")
        logger.info(f"  [TXT] txtPrb: '{txtPrb[:100] if txtPrb else 'None'}...'")

        try:
            if not self.is_available or not self.ai_agent:
                logger.warning("FilterDetectionService: недоступен (нет AIAgentService)")
                return {
                    'status': 'error',
                    'error': 'Service unavailable'
                }

            # Используем txtPrb или message_text
            problem_description = txtPrb if txtPrb else message_text

            # ====================================================================
            # ВЫЗЫВАЕМ 3 ПРОМПТА ПАРАЛЛЕЛЬНО
            # ====================================================================
            # ИЗМЕНЕНО (2026-03-22): category ПЕРЕВКЛЮЧЕН
            logger.info(f"FilterDetectionService: запускаем 3 промпта параллельно...")

            # Создаем промпты
            # ИСПРАВЛЕНО (2026-02-05): Добавлен await (методы теперь async)
            prompt_incident = await self._create_incident_type_prompt(problem_description)
            prompt_location = await self._create_location_type_prompt(problem_description)
            # ИЗМЕНЕНО (2026-03-22): category ПЕРЕВКЛЮЧЕН
            prompt_category = await self._create_category_prompt(problem_description)

            # Вызываем LLM для каждого фильтра
            # ИСПРАВЛЕНО (2026-03-07): Передаём уникальный service_name для каждого фильтра
            # ИЗМЕНЕНО (2026-03-22): category добавлен в параллельное выполнение
            incident_result, location_result, category_result = await asyncio.gather(
                self._call_llm_for_filter(prompt_incident, 'incident_type', session_id, message_id),
                self._call_llm_for_filter(prompt_location, 'location_type', session_id, message_id),
                self._call_llm_for_filter(prompt_category, 'category', session_id, message_id)
            )

            # ====================================================================
            # СОБИРАЕМ ИТОГОВЫЙ JSON
            # ====================================================================
            filters = {
                'incident_type': incident_result['value'],
                'location_type': location_result['value'],
                'category': category_result['value']
            }

            # Общая уверенность = минимум из трех
            # ИЗМЕНЕНО (2026-03-22): category добавлен в расчет confidence
            confidence = min(
                incident_result['confidence'],
                location_result['confidence'],
                category_result['confidence']
            )

            # Объединяем reasoning
            reasoning = f"incident_type: {incident_result['reasoning']} | location_type: {location_result['reasoning']} | category: {category_result['reasoning']}"

            logger.info(
                f"FilterDetectionService: определены фильтры: "
                f"incident_type={filters['incident_type']} (conf={incident_result['confidence']}), "
                f"location_type={filters['location_type']} (conf={location_result['confidence']}), "
                f"category={filters['category']} (conf={category_result['confidence']}), "
                f"overall_confidence={confidence}"
            )

            return {
                'status': 'success',
                'filters': filters,
                'confidence': confidence,
                'reason': reasoning,
                'details': {
                    'incident_type': incident_result,
                    'location_type': location_result,
                    'category': category_result
                }
            }

        except Exception as e:
            logger.error(f"FilterDetectionService: Ошибка: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }

    # ========================================================================
    # СТАРЫЙ МЕТОД (для совместимости)
    # ========================================================================

    def _create_filter_detection_prompt(self, message_text: str, dialog_history: List[Dict], txtPrb: str = None) -> str:
        """УСТАРЕЛ: Используйте _create_incident_type_prompt, _create_location_type_prompt, _create_category_prompt"""
        problem_description = txtPrb if txtPrb else message_text
        categories_str = ", ".join([f'"{cat}"' for cat in self.categories_list])
        history_text = ""
        if dialog_history:
            for msg in dialog_history[-3:]:
                role = "П" if msg.get('role') == 'user' else "Б"
                text = msg.get('text', '')[:50]
                history_text += f"{role}: {text}...\n"

        # Переменные для f-string (будут заполнены LLM по алгоритму в промпте)
        OBJ = ""
        EVENT = ""
        PLACE = ""
        reasoning_txt = ""
        последствия = ""
        incident_type = ""
        incident_confidence = ""
        SCOPE = ""
        location_type = ""
        location_confidence = ""
        M_EVENT = {}
        M_PLACE = {}
        M_OBJ = {}
        M_CANDIDATE = {}
        Z1_cat = ""
        Z1 = 0.0
        total = 0.0
        ostatok = 0.0
        category = ""
        category_confidence = ""

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

последствия = "[опиши последствия: угроза жизни/здоровью/имуществу или отсутствие угрозы]"
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
# ИСПРАВЛЕНО (2026-01-23): Определяем SCOPE только по ЯВНОМУ указанию в PLACE
# НЕ угадываем по OBJ (см. первый промпт _create_location_type_prompt)
SCOPE = null

# 3.1 Явная локация в PLACE?
# ИСПРАВЛЕНО (2026-01-23): Добавлен предлог "в"/"на" для точности (см. первый промпт)
если PLACE содержит ("в квартир"/"в ванн"/"в кухн"/"в спальн"/"в туалет"/"на балкон"):
    SCOPE="внутри"
иначе если PLACE содержит ("в подъезд"/"в лифт"/"в подвал"/"на крыш"/"на чердак"/"во двор"/"на фасад"):
    SCOPE="вне"

# 3.2 location_type
# ИСПРАВЛЕНО (2026-01-23): Исправлена ошибка LLM которая выдумывала "Индивидуальное по умолчанию"
# СТАРЫЙ ВАРИАНТ (ошибочный - LLM игнорировал else null):
# location_type = "Индивидуальное" если SCOPE=="внутри" else "Общедомовое" если "вне" else null
# location_confidence = "1.0" если не null else "0.5"
# НОВЫЙ ВАРИАНТ (явная проверка SCOPE=="вне" вместо "вне"):
location_type = null
location_confidence = "0.5"
если SCOPE=="внутри":
    location_type="Индивидуальное"
    location_confidence="1.0"
иначе если SCOPE=="вне":
    location_type="Общедомовое"
    location_confidence="1.0"
# ⛔ Если SCOPE=null, location_type остается null (НЕ выдумывать "по умолчанию"!)

reasoning_txt += " | Шаг3: PLACE=[" + PLACE + "] → SCOPE=" + SCOPE + " → location_type=" + location_type + "(" + location_confidence + ")"

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
# ИСПРАВЛЕНО (2026-01-26): Убран M_PLACE из умножения!
# ПРИЧИНА: Если PLACE не указан, M_PLACE=[0,0,...] → M_CANDIDATE=[0,0,...] → category=null
# НОВАЯ ФОРМУЛА: M_CANDIDATE = M_OBJ * M_EVENT (место не влияет на категорию!)
for cat in CATEGORIES:
    M_CANDIDATE[cat] = round(M_OBJ[cat] * M_EVENT[cat], 3)
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
  "location_type": """ + location_type +""",
  "location_confidence": """ + location_confidence + """",
  "category": """ + category + """",
  "category_confidence": """ + category_confidence + """",
  "reasoning": """ + reasoning_txt + """
}}"""
        return prompt

    # ========================================================================
    # МЕТОД РАНЖИРОВАНИЯ КАНДИДАТОВ
    # ========================================================================

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

            # ИСПРАВЛЕНО (2026-02-24): Передаем service_name для отслеживания
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider=None,  # Используем провайдер из env (DEFAULT_LLM_PROVIDER)
                model=None,  # Используем модель по умолчанию из .env
                session_id=session_id,
                service_name='FilterDetectionService'
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
