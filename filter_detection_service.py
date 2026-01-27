#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FilterDetectionService - микросервис определения фильтров через LLM

ИСПРАВЛЕНО (2026-01-20): Разбит на 3 отдельных промпта:
- incident_type (Инцидент/Запрос)
- location_type (Индивидуальное/Общедомовое)
- category (категория проблемы) - ОТКЛЮЧЕН с 2026-01-27

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
        """Загружает справочные данные из БД для промпта"""
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
                    # Загружаем уникальные категории
                    cursor.execute("""
                        SELECT DISTINCT rc.category_name
                        FROM services_catalog sc
                        JOIN ref_categories rc ON sc.category_id = rc.category_id
                        WHERE rc.category_name IS NOT NULL AND rc.category_name != ''
                        ORDER BY rc.category_name
                    """)
                    self.categories_list = [row[0] for row in cursor.fetchall()]

                    # Загружаем примеры объектов
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

    # ========================================================================
    # ПРОМПТ 1: incident_type (Инцидент/Запрос)
    # ========================================================================

    def _create_incident_type_prompt(self, txtPrb: str) -> str:
        """Создание промпта для определения incident_type"""
        # Переменные для f-string (будут заполнены LLM по алгоритму в промпте)
        OBJ = ""
        EVENT = ""
        PLACE = ""
        reasoning_txt = ""
        последствия = ""
        incident_type = ""
        incident_confidence = ""

        # ========================================================================
        # СТАРЫЙ ПРОМПТ (до 2026-01-23, без few-shot примеров)
        # ========================================================================
        # prompt_old = f"""## Роль
        # Ты — строгий алгоритмический классификатор типа обращения. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.
        #
        # ## Входные данные
        # TXT_PRB = "{txtPrb}"
        #
        # ## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)
        # (далее алгоритм без изменений...)
        # """

        # ========================================================================
        # НОВЫЙ ПРОМПТ (с 2026-01-23, добавлены few-shot примеры из БД)
        # ========================================================================
        prompt = f"""## Роль
Ты — строгий алгоритмический классификатор типа обращения. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txtPrb}"

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. ИЕРАРХИЯ УГРОЗ
**ПРИМЕР "течёт труба": угроза имуществу(вода) → Инцидент(0.8)**

последствия = "[опиши последствия: угроза жизни/здоровью/имуществу или отсутствие угрозы]"
incident_type = null
incident_confidence = "0.5"

# 2.0 Пожарная безопасность? (огнетушитель/эвакуация/пожарный выход/сигнализация/пожарный кран)
# КРИТИЧЕСКОЕ ПРАВИЛО: ВСЕ обращения по пожарной безопасности = Инцидент(1.0)
если TXT_PRB содержит ("огнетуш" или "эвакуац" или "эвакуационн" или "пожарный выход" или "пожарная сигнализац" или "пожарн" или "пожарной" или "пожарный кран" или "пожарный щит" или "систем пожаротушен" или "дымокур" или "дымоудален" или "противопожарн" или "сигнализ" или "пожароопас"):
    incident_type="Инцидент"; incident_confidence="1.0"
    reasoning_txt += " | 2.0: пожарная безопасность → Инцидент(1.0)"

# 2.1 Угроза жизни? (потоп/обрушение/пожар/газ)
если incident_confidence=="0.5" и последствия содержит ("потоп" или "обрушение" или "пожар" или "газ" или "взрыв" или "заваливание"):
    incident_type="Инцидент"; incident_confidence="1.0"
    reasoning_txt += " | 2.1: [" + последствия + "] → Инцидент"

# 2.2 Угроза здоровью? (плесень/травма/электричество)
если incident_confidence=="0.5" и последствия содержит ("плесень" или "травма" или "электричество" или "озон" или "угарный"):
    incident_type="Инцидент"; incident_confidence="0.9"
    reasoning_txt += " | 2.2: [" + последствия + "] → Инцидент"

# 2.3 Угроза имуществу? (повреждение квартиры/затопление)
если incident_confidence=="0.5" и последствия содержит ("затоплен" или "поврежден" или "отсутств" или "нет свет" или "нет вод" или "нет тепл" или "нет газ"):
    incident_type="Инцидент"; incident_confidence="0.8"
    reasoning_txt += " | 2.3: [" + последствия + "] → Инцидент"

# 2.4 Запрос без срочности?
если incident_confidence=="0.5":
    incident_type="Запрос"; incident_confidence="0.7"
    reasoning_txt += " | 2.4: Запрос без угроз"

reasoning_txt += " | incident_type=" + incident_type + "(" + incident_confidence + ")"

### Шаг3. JSON
Верни JSON в формате:
{{"incident_type": [значение incident_type], "confidence": [значение incident_confidence], "reasoning": [значение reasoning_txt]}}"""
        return prompt

    # ========================================================================
    # ПРОМПТ 2: location_type (Индивидуальное/Общедомовое)
    # ========================================================================

    def _create_location_type_prompt(self, txtPrb: str) -> str:
        """Создание промпта для определения location_type"""
        # Переменные для f-string (будут заполнены LLM по алгоритму в промпте)
        OBJ = ""
        EVENT = ""
        PLACE = ""
        reasoning_txt = ""
        SCOPE = ""
        location_type = ""
        location_confidence = ""

        # ========================================================================
        # СТАРЫЙ ПРОМПТ (до 2026-01-23, без few-shot примеров)
        # ========================================================================
        # prompt_old = f"""## Роль
        # Ты — строгий алгоритмический классификатор локации. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.
        #
        # ## Входные данные
        # TXT_PRB = "{txtPrb}"
        #
        # ## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)
        # (далее алгоритм без изменений...)
        # """

        # ========================================================================
        # НОВЫЙ ПРОМПТ (с 2026-01-23, добавлены few-shot примеры из БД)
        # ========================================================================
        prompt = f"""## Роль
Ты — строгий алгоритмический классификатор локации. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txtPrb}"

## ПРИМЕРЫ ИЗ БАЗЫ ДАННЫХ (проанализированы все 78 услуг)

ОБЩЕДОМОВОЕ (выборка из 47 услуг):
- "Нет света во всем доме" → Общедомовое
- "Нет света в части дома" → Общедомовое
- "Нет горячей воды во всём доме" → Общедомовое
- "Прорыв в системе отопления общедомовой" → Общедомовое
- "Общедомовой прорыв труб и затопление" → Общедомовое
- "Искрение, замыкание электрощитов и ВРУ" → Общедомовое
- "Не работает домофон" → Общедомовое
- "Лифт не работает, двери застряли" → Общедомовое
- "Уборка подъездов, лестничных клеток" → Общедомовое
- "Протечка крыши, затекание в квартиру" → Общедомовое
- "Мусорные контейнеры переполнены" → Общедомовое
- "Очистка лотков и приямков водоотведения" → Общедомовое

ИНДИВИДУАЛЬНОЕ (выборка из 31 услуги):
- "Нет света индивидуальное" → Индивидуальное
- "Прорыв труб в квартире" → Индивидуальное
- "Протечка батареи/радиатора в квартире" → Индивидуальное
- "Затопление от соседей" → Индивидуальное
- "Замена/поверка водомерных счётчиков" → Индивидуальное
- "Полотенцесушитель не греет/холодный" → Индивидуальное
- "Делопроизводство" → Индивидуальное
- "Технические характеристики и информация о состоянии дома" → Индивидуальное

⛔ ВСЕ Информационные запросы → Индивидуальное (12/12 услуг)

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. Определи SCOPE (внутри/вне)
SCOPE = null

# 2.1 Явная локация?
# ИСПРАВЛЕНО (2026-01-23): Добавлен предлог "в"/"на" для точности
# ПРИМЕР ОШИБКИ: "холодная вода" содержит "ванн" → внутри (НЕВЕРНО!)
# ПРАВИЛЬНО: "в ванной" → "в ванной" содержит "в" + "ванн" → внутри (ВЕРНО!)
если PLACE содержит ("в квартир"/"в ванн"/"в кухн"/"в спальн"/"в туалет"/"на балкон"):
    SCOPE="внутри"
reasoning_txt += " | 2.1: PLACE=[" + PLACE + "] → SCOPE=внутри"

иначе если PLACE содержит ("в подъезд"/"в лифт"/"в подвал"/"на крыш"/"на чердак"/"во двор"/"на фасад"):
    SCOPE="вне"
    reasoning_txt += " | 2.1: PLACE=[" + PLACE + "] → SCOPE=вне"

# 2.2 Если SCOPE=null, используй OBJ
# ИСПРАВЛЕНО (2026-01-23): Шаг 2.2 ЗАКОММЕНТИРОВАН (неугадываем локацию!)
# ПРИЧИНА: "вода", "кран" и т.п. НЕ являются явным указанием локации
# ПРИМЕР ОШИБКИ: "нет холодной воды" → OBJ="вода" → SCOPE="внутри" → Индивидуальное
#           Но правильная услуга "Нет холодной воды во всём доме" → Общедомовое!
# РЕШЕНИЕ: Если PLACE не указан явно (шаг 2.1), оставляем SCOPE=null
#          Это приведет к location_type=null → в MainAgent спросит "Где именно?"
# СТАРЫЙ ВАРИАНТ (приводил к ошибкам):
# иначе если OBJ содержит ("кран"/"смеситель"/"унитаз"/"ванна"/"розетка"/"дверь межкомнат"):
#     SCOPE="внутри"
#     reasoning_txt += " | 2.2: OBJ=[" + OBJ + "] → SCOPE=внутри"
# иначе если OBJ содержит ("лифт"/"домофон"/"крыш"/"подвал"/"стояк"/"фасад"/"двор"):
#     SCOPE="вне"
#     reasoning_txt += " | 2.2: OBJ=[" + OBJ + "] → SCOPE=вне"

# 2.3 Если всё ещё null, используй EVENT
иначе если EVENT содержит ("сверху"/"с потолка"/"стена"/"фундамент"/"межпанель"):
    SCOPE="вне"
    reasoning_txt += " | 2.3: EVENT=[" + EVENT + "] → SCOPE=вне"

### Шаг3. location_type
# ⛔⛔⛔ КРИТИЧЕСКИ ВАЖНО: В блоке иначе ЯВНО присваиваем location_type=null!
# КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать "Индивидуальное" или "Общедомовое" по умолчанию!
# ПРИМЕР: "нет воды" → PLACE не содержит "в квартир"/"во дворе" → SCOPE=null → location_type=null
#          НЕ ДОПУСКАЙ: "location_type=Индивидуальное по умолчанию" ❌❌❌
location_type = null
location_confidence = "0.5"

если SCOPE=="внутри":
    location_type="Индивидуальное"
    location_confidence="1.0"
    reasoning_txt += " | Шаг3: SCOPE=внутри → Индивидуальное(1.0)"
иначе если SCOPE=="вне":
    location_type="Общедомовое"
    location_confidence="1.0"
    reasoning_txt += " | Шаг3: SCOPE=вне → Общедомовое(1.0)"
иначе:
    # ⛔⛔⛔ STOP! Если SCOPE=null, location_type ТОЛЬКО null!
    # НЕ вставляй "Индивидуальное" или "Общедомовое" - это КАТЕГОРИЧЕСКИ ОШИБКА!
    location_type=null
    location_confidence="0.5"
    reasoning_txt += " | Шаг3: SCOPE=null → location_type=null(0.5)"

### Шаг4. JSON
{{
  "location_type": """ + location_type + """",
  "confidence": """ + location_confidence + """",
  "reasoning": """ + reasoning_txt + """
}}"""
        return prompt

    # ========================================================================
    # ПРОМПТ 3: category (категория проблемы)
    # ========================================================================

    def _create_category_prompt(self, txtPrb: str) -> str:
        """Создание промпта для определения category"""
        # Формируем список категорий
        categories_str = ", ".join([f'"{cat}"' for cat in self.categories_list])

        # Переменные для f-string (будут заполнены LLM по алгоритму в промпте)
        OBJ = ""
        EVENT = ""
        PLACE = ""
        reasoning_txt = ""
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

        # ========================================================================
        # СТАРЫЙ ПРОМПТ (до 2026-01-23, без few-shot примеров)
        # ========================================================================
        # prompt_old = f"""## Роль
        # Ты — строгий алгоритмический классификатор категории. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.
        #
        # ## Входные данные
        # TXT_PRB = "{txtPrb}"
        # CATEGORIES = [{categories_str}]
        #
        # ## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)
        # (далее сложный алгоритм с матрицами...)
        # """

        # ========================================================================
        # НОВЫЙ ПРОМПТ (с 2026-01-23, добавлены few-shot примеры из БД)
        # ========================================================================
        prompt = f"""## Роль
Ты — строгий алгоритмический классификатор категории. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txtPrb}"
CATEGORIES = [{categories_str}]

## ПРИМЕРЫ ИЗ БАЗЫ ДАННЫХ (проанализированы все 78 услуг)

Электричество (9 услуг):
- "Нет света во всем доме" → Электричество
- "Нет света в части дома" → Электричество
- "Искрение, замыкание электрощитов и ВРУ" → Электричество
- "Нет света индивидуальное" → Электричество
- "Не работает домофон" → Электричество

Водоснабжение (10 услуг):
- "Прорыв труб в квартире" → Водоснабжение
- "Общедомовой прорыв труб и затопление" → Водоснабжение
- "Нет горячей воды во всём доме" → Водоснабжение
- "Нет холодной воды во всём доме" → Водоснабжение
- "Затопление от соседей" → Водоснабжение
- "Полотенцесушитель не греет/холодный" → Водоснабжение

Отопление (7 услуг):
- "Отсутствие отопления" → Отопление
- "Прорыв в системе отопления общедомовой" → Отопление
- "Проверка и регулировка систем отопления" → Отопление
- "Протечка батареи/радиатора в квартире" → Отопление

Конструктив (9 услуг):
- "Протечка крыши, затекание в квартиру" → Конструктив
- "Повреждения крыши/желобов/водосточных труб" → Конструктив
- "Ремонт стен и перекрытий" → Конструктив
- "Ремонт крыши/желобов/водосточных труб" → Конструктив

Санитария (10 услуг):
- "Очистка лотков и приямков водоотведения" → Санитария
- "Мусорные контейнеры переполнены" → Санитария
- "Снег и наледь на территории" → Санитария
- "Засор ливнёвой канализации/дренажных систем" → Санитария
- "Уборка подъездов, лестничных клеток" → Санитария

Информационные запросы (12 услуг):
- "Делопроизводство" → Информационные запросы
- "Технические характеристики и информация о состоянии дома" → Информационные запросы
- "Запросы по квартирным платежам" → Информационные запросы
- "Проведение общего собрания собственников" → Информационные запросы

Пожарная безопасность (6 услуг):
- "Пожар/возгорание общедомовой" → Пожарная безопасность
- "Пожар в квартире" → Пожарная безопасность
- "Сработала пожарная сигнализация" → Пожарная безопасность

Озеленение (2 услуги):
- "Упало дерево/ветка на провода/дом/дорога" → Озеленение
- "Уход за зелёными зонами, газонами" → Озеленение

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. Category (ВСЕ CATEGORIES! sum релев=1.0, impossible=0.0)

M_EVENT = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные: распредели sum=1.0
# ПРИМЕР: M_EVENT["Водоснабжение"]=0.4; M_EVENT["Канализация"]=0.3; ...
reasoning_txt += " | Шаг2: M_EVENT=" + str(M_EVENT) + " (sum релев=1.0)"

M_PLACE = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные в PLACE sum=1.0 (равно если неоднозначно)
# ПРИМЕР: M_PLACE["Водоснабжение"]=0.33; M_PLACE["Канализация"]=0.33; ...
reasoning_txt += " | M_PLACE=" + str(M_PLACE) + " (sum=1.0)"

M_OBJ = {{cat: 0.0 for cat in CATEGORIES}}
# ПРИМЕР: M_OBJ["Водоснабжение"]=0.33; M_OBJ["Канализация"]=0.33; ...
reasoning_txt += " | M_OBJ=" + str(M_OBJ) + " (sum=1.0)"

M_CANDIDATE = {{}}
# ИСПРАВЛЕНО (2026-01-26): Убран M_PLACE из умножения!
# ПРИЧИНА: Если PLACE не указан, M_PLACE=[0,0,...] → M_CANDIDATE=[0,0,...] → category=null
# НОВАЯ ФОРМУЛА: M_CANDIDATE = M_OBJ * M_EVENT (место не влияет на категорию!)
for cat in CATEGORIES:
    M_CANDIDATE[cat] = round(M_OBJ[cat] * M_EVENT[cat], 3)
reasoning_txt += " | M_CANDIDATE=" + str(M_CANDIDATE)

Z1_cat = max(M_CANDIDATE, key=M_CANDIDATE.get)
Z1 = M_CANDIDATE[Z1_cat]
total = sum(M_CANDIDATE.values())
ostatok = total - Z1
category = null
category_confidence = "0.5"
if Z1 > ostatok * 0.7:
    category = Z1_cat
    category_confidence = str(round(Z1, 1))
reasoning_txt += " | Z1=" + Z1_cat + "(" + str(Z1) + "), total=" + str(total) + ", остаток=" + str(ostatok) + ", " + str(Z1) + ">" + str(ostatok*0.7) + "=" + (ДА/НЕТ) + " → category=" + str(category) + "(" + category_confidence + ")"

### Шаг3. JSON
{{
  "category": """ + str(category) + """,
  "confidence": """ + category_confidence + """,
  "reasoning": """ + reasoning_txt + """
}}"""
        return prompt

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

            # Вызываем LLM
            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                session_id=session_id,
                message_id=message_id
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
        Определяет все фильтры через 2 отдельных промпта

        ИСПРАВЛЕНО (2026-01-20): Разбит на 3 промпта (incident_type, location_type, category)
        ИСПРАВЛЕНО (2026-01-27): Category ОТКЛЮЧЕН, используется только 2 промпта

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
                        'category': None  # ОТКЛЮЧЕН
                    },
                    'confidence': float,
                    'reason': str,
                    'details': {
                        'incident_type': {...},
                        'location_type': {...},
                        'category': {...}  # Всегда None
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
            # ВЫЗЫВАЕМ 2 ПРОМПТА ПАРАЛЛЕЛЬНО (category ОТКЛЮЧЕН)
            # ====================================================================
            logger.info(f"FilterDetectionService: запускаем 2 промпта параллельно (category ОТКЛЮЧЕН)...")

            # Создаем промпты
            prompt_incident = self._create_incident_type_prompt(problem_description)
            prompt_location = self._create_location_type_prompt(problem_description)
            # prompt_category = self._create_category_prompt(problem_description)  # ОТКЛЮЧЕНО

            # Вызываем LLM для каждого фильтра
            incident_result, location_result = await asyncio.gather(
                self._call_llm_for_filter(prompt_incident, 'incident_type', session_id, message_id),
                self._call_llm_for_filter(prompt_location, 'location_type', session_id, message_id)
                # category ОТКЛЮЧЕН
            )

            # Фиктивный результат для category (чтобы не ломать код)
            category_result = {
                'value': None,
                'confidence': 0.0,
                'reasoning': 'Category detection ОТКЛЮЧЕН'
            }

            # ====================================================================
            # СОБИРАЕМ ИТОГОВЫЙ JSON
            # ====================================================================
            filters = {
                'incident_type': incident_result['value'],
                'location_type': location_result['value'],
                'category': category_result['value']
            }

            # Общая уверенность = минимум из двух (category ОТКЛЮЧЕН)
            confidence = min(
                incident_result['confidence'],
                location_result['confidence']
                # category_result['confidence']  # ОТКЛЮЧЕНО
            )

            # Объединяем reasoning (category ОТКЛЮЧЕН)
            reasoning = f"incident_type: {incident_result['reasoning']} | location_type: {location_result['reasoning']} | category: ОТКЛЮЧЕН"

            logger.info(
                f"FilterDetectionService: определены фильтры: "
                f"incident_type={filters['incident_type']} (conf={incident_result['confidence']}), "
                f"location_type={filters['location_type']} (conf={location_result['confidence']}), "
                f"category={filters['category']} (ОТКЛЮЧЕН), "
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

            response, usage_info = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                session_id=session_id
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
