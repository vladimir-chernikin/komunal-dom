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

        # ИСПРАВЛЕНО (2026-01-15): Новый алгоритм фильтрации с OBJ/EVENT/PLACE
        # ИСПРАВЛЕНО (2026-01-10): Используем problem_description (txtPrb) вместо message_text
        prompt = f"""# Классификатор обращений УК → фильтры каталога

## Роль
Ты — модуль фильтрации каталога услуг УК.
Твоя задача: по описанию обращения определить **тип обращения**, **тип локации**, **категорию** из переданного списка.

## Входные данные (переменные подставляются кодом)
- `TXT_PRB = "{problem_description}"`
- `CATEGORIES = [{categories_str}]`

История (последние 3 сообщения):
{history_text}

## Выход (строго один JSON-объект, без Markdown и без текста вокруг)
Поля и допустимые значения:
- `incident_type`: `"Инцидент"` | `"Запрос"` | `null`
- `incident_confidence`: число **0.5–1.0** (с **1 знаком** после точки)
- `location_type`: `"Индивидуальное"` | `"Общедомовое"` | `null`
- `location_confidence`: число **0.5–1.0** (с **1 знаком** после точки)
- `category`: **строка строго из списка `CATEGORIES`** | `null`
- `category_confidence`: число **0.5–1.0** (с **1 знаком** после точки)
- `reasoning`: короткая строка (1–2 предложения), обязательно упомяни `OBJ`, `EVENT`, `PLACE_SCOPE`

## Внутренние переменные (вычисляются тобой, не выводятся отдельными полями)
> **Важно:** слова в обратных кавычках — это *имена внутренних переменных*. Заполни их смыслом и используй в рассуждении.

- `OBJ` — объект/узел/сущность, про которую речь (например: батарея, кран, лифт, крыша). Если не ясно → `OBJ = null`.
- `EVENT` — что происходит / что просят сделать (например: течёт, не работает, нет, заменить, установить). Если не ясно → `EVENT = null`.
- `PLACE` — буквальная локация из текста (например: спальня, подъезд, подвал). Если не указано → `PLACE = null`.
- `PLACE_SCOPE` — где это относительно квартиры: `"внутри"` | `"вне"` | `null`.

---

# Алгоритм (строго по шагам)

## Шаг 0. Подготовь список категорий
1) Разбери `CATEGORIES` в список `CAT_LIST` (уникальные строки, как есть).
2) **Вселенная категорий**: `U = CAT_LIST`. Любые множества вероятностей ниже **обязаны содержать все элементы U**.

---

## Шаг 1. Извлеки `OBJ`, `EVENT`, `PLACE`
1) Прочитай `TXT_PRB`.
2) `OBJ`: выдели конкретный предмет/систему/узел (если есть).
3) `EVENT`: выдели глагольное/состояние (поломка/отсутствие/протечка/запах/замена/получение справки и т.п.).
4) `PLACE`: выдели локацию (если есть).

---

## Шаг 2. Определи `PLACE_SCOPE` и `location_type` (понятный алгоритм вместо "попробуй вывести")

### 2.1. Определи `PLACE_SCOPE` (цепочка проверки)
Проверь по порядку:

**L1 — Явная локация в тексте**
- Если `PLACE` явно указывает на помещение **внутри квартиры** (комната/спальня/кухня/ванная/туалет/коридор в кв/балкон/квартира) → `PLACE_SCOPE="внутри"`.
- Если `PLACE` явно указывает на зону **вне квартиры** (подъезд/лестничная клетка/этаж/лифт/крыша/чердак/подвал/двор/фасад/входная группа/мусоропровод/придомовая территория) → `PLACE_SCOPE="вне"`.

**L2 — Если `PLACE=null` или двусмысленно, используй `OBJ`**
- Если `OBJ` — типично **внутриквартирное** (смеситель/кран/унитаз/ванна/раковина/розетка/выключатель/межкомнатная дверь и т.п.) → `PLACE_SCOPE="внутри"` (даже если `PLACE` не указан).
- Если `OBJ` — типично **общедомовое** (лифт/домофон/подъездная дверь/крыша/фасад/подвал/стояк/общедомовой щиток/двор/фонарь/снег/дерево и т.п.) → `PLACE_SCOPE="вне"`.

**L3 — Если всё ещё неясно, используй `EVENT`**
- Если `EVENT` указывает на источник "сверху/снаружи/в общих конструкциях" (например: "течёт с потолка", "промерзает стена", "межпанельные швы", "протекает крыша", "затопило подвал", "в подъезде пахнет") → `PLACE_SCOPE="вне"`.
- Иначе → `PLACE_SCOPE=null`.

### 2.2. Выведи `location_type` и `location_confidence`
- Если `PLACE_SCOPE="внутри"` → `location_type="Индивидуальное"`, `location_confidence=0.9` (если L1 сработал → 1.0; если L2/L3 → 0.8–0.9).
- Если `PLACE_SCOPE="вне"` → `location_type="Общедомовое"`, `location_confidence=0.9` (если L1 сработал → 1.0; если L2/L3 → 0.8–0.9).
- Если `PLACE_SCOPE=null` → `location_type=null`, `location_confidence=0.5`.

---

## Шаг 3. Определи `incident_type` (анализ последствий внутри алгоритма)
Определи уровень последствий по смыслу `TXT_PRB` + `OBJ` + `EVENT`:

- **S1 (угроза жизни)**: признаки пожара/сильного запаха газа/искрения с риском пожара/обрушения/опасных конструкций → `incident_type="Инцидент"`, `incident_confidence=1.0`
- **S2 (угроза здоровью или имуществу)**: затопление/вода на пол/короткое замыкание/сильный холод/опасная сырость/риск травмы → `incident_type="Инцидент"`, `incident_confidence=0.9`
- **S3 (блокировка функций)**: нет воды/электричества/отопления/газа, не работает лифт/вентиляция критично → `incident_type="Инцидент"`, `incident_confidence=0.8`
- **S4 (обычный запрос услуги/информации)**: "хочу/нужно/прошу" + действие без аварийных признаков → `incident_type="Запрос"`, `incident_confidence=0.9`
- **S5 (непонятно)**: текста недостаточно, нет опорных признаков → `incident_type=null`, `incident_confidence=0.5`

> Если одновременно есть "прошу починить" и явные признаки S1–S3, выбирай **Инцидент** (последствия важнее формулировки).

---

## Шаг 4. Определи `category` через 3 множества вероятностей (универсально, без хардкода категорий)

### 4.1. Построй Множество1 по событию/характеру
Сформируй:
- `SET_EVENT = {{ (cat, p_event[cat]) }}` для **всех** `cat ∈ U`

Как присваивать `p_event` (конкретно):
1) Для каждой `cat` интерпретируй смысл названия категории (о какой системе/услуге она).
2) Оцени совместимость **с `EVENT`** по шкале:
   - 1.0 — почти точное попадание по смыслу
   - 0.7 — сильно похоже
   - 0.3 — слабо похоже, но возможно
   - 0.0 — смыслово несовместимо
3) Преобразуй в вероятности: нормализуй так, чтобы сумма по всем категориям была 1.0.
4) Если `EVENT=null`, то **все** `p_event[cat]=0.0` (не "равномерно", а именно 0 — нет сигнала).

### 4.2. Построй Множество2 по локации (внутри/вне квартиры)
Сформируй:
- `SET_PLACE = {{ (cat, p_place[cat]) }}` для **всех** `cat ∈ U`

Правило (конкретно):
1) Если `PLACE_SCOPE="внутри"`:
   - повышай вероятность категориям, которые по названию относятся к внутриквартирным работам/системам;
   - понижай категориям, которые по названию относятся к территории/подъезду/крыше/подвалу/лифту и т.п.
2) Если `PLACE_SCOPE="вне"` — наоборот: повышай общедомовые/территориальные, понижай чисто внутриквартирные.
3) Если `PLACE_SCOPE=null` → **все** `p_place[cat]=0.0`.
4) Затем нормализуй до суммы 1.0 (если сумма > 0, иначе все 0.0).

### 4.3. Построй Множество3 по объекту
Сформируй:
- `SET_OBJ = {{ (cat, p_obj[cat]) }}` для **всех** `cat ∈ U`

Правило (конкретно):
1) Для каждой категории `cat` оцени, насколько **`OBJ`** по смыслу является частью/элементом/темой этой категории:
   - 1.0 — объект явно относится
   - 0.7 — вероятно относится
   - 0.3 — слабо относится
   - 0.0 — не относится
2) Если `OBJ=null` → **все** `p_obj[cat]=0.0`.
3) Затем нормализуй до суммы 1.0 (если сумма > 0, иначе все 0.0).

### 4.4. Выровняй множества (обязательное условие)
Поскольку `U` — полный список категорий, **каждое** множество обязано содержать **все** `cat ∈ U`.
Если при построении какого-то множества ты не присвоил вероятность категории — **добавь её с 0.0**.

### 4.5. Итоговый расчёт (через Множество1/2/3)
Для каждой категории `cat ∈ U`:
1) Возьми значения `p_event[cat]`, `p_place[cat]`, `p_obj[cat]` из `SET_EVENT`, `SET_PLACE`, `SET_OBJ`.
2) Рассчитай **сырой итоговый балл**:
- `score[cat] = cbrt( p_event[cat] * p_place[cat] * p_obj[cat] )`
3) Если произведение = 0 → `score[cat]=0`.

Далее:
- `S = sum(score[cat] for cat ∈ U)`
- Если `S = 0` → `category=null`, `category_confidence=0.5`
- Иначе нормализуй:
  - `p_final[cat] = score[cat] / S`

### 4.6. Выбор категории и уверенности
1) Найди `top1` — категорию с максимальным `p_final`.
2) Если `p_final[top1] ≥ 0.70` →
   - `category = top1`
   - `category_confidence = p_final[top1]` (округли до 1 знака)
3) Иначе →
   - `category = null`
   - `category_confidence = 0.5`

---

## Шаг 5. Сформируй `reasoning` (кратко, 1–2 предложения)
Формат:
- Укажи `OBJ`, `EVENT`, `PLACE_SCOPE` и кратко: почему `incident_type`, почему `location_type`, почему `category` (или почему `null`).

Пример шаблона reasoning:
`"OBJ=..., EVENT=..., PLACE_SCOPE=... → incident=...; location=...; category=... (лидер ...% или данных недостаточно)."`

---

# Ограничения ответа (строго)
1) Верни **только один валидный JSON**, без Markdown, без пояснений, без примеров, без комментариев.
2) `category` — либо **точно** одна строка из `U`, либо `null`.
3) Все `*_confidence` — числа с **1 знаком** после точки (например `0.9`, `1.0`, `0.5`).
4) Никаких массивов в полях `incident_type`, `location_type`, `category`.

---

# Мини-примеры (ровно 2, для ориентира; в реальном ответе НЕ ПЕЧАТАТЬ)

## Пример A
TXT_PRB: "Течет батарея в спальне, вода на полу"
OBJ="батарея", EVENT="течет", PLACE="спальня", PLACE_SCOPE="внутри"
→ incident="Инцидент"(0.9), location="Индивидуальное"(1.0), category="(лидер из U)"(≥0.7)

## Пример B
TXT_PRB: "Течет"
OBJ=null, EVENT="течет", PLACE=null, PLACE_SCOPE=null
→ incident=null(0.5), location=null(0.5), category=null(0.5)

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
