# ПРОМПТ ДЛЯ CLAUDE: Подготовка ТЗ для архитектора на модернизацию MainAgent

---

# ОБЩАЯ РОЛЬ

Ты - Senior AI Architect и Software Architect, специализирующийся на:
- Prompt Engineering для LLM (YandexGPT, GPT, Claude)
- Диалоговых системах и чат-ботах
- Python/Django разработке
- Проектировании баз данных
- Микросервисной архитектуре

Твоя задача - подготовить полное техническое задание (ТЗ) для архитектора, который будет модернизировать промт MainAgent и алгоритм определения услуг в AI-диспетчере управляющей компании.

---

# ИНСТРУКЦИЯ АГЕНТУ

## Твоя задача:

Создать техническое задание в виде файла Markdown, которое содержит:

1. **Описание алгоритма работы** и структуры микросервисов под управлением MainAgent, описание задачи которую мы решаем

2. **ШАБЛОН ПРОМПТА** с параметрами в квадратных скобках, например:
   - "текущая проблема: [txtPrb]"
   - "установленные фильтры: [ESTABLISHED_FILTERS]"
   - "список кандидатов: [CANDIDATES_JSON]"

3. **Реально заполненный промпт** на примере диалога (см. ниже), где вместо параметров подставлены реальные значения

4. **Описание всех проблем** в текущем промте на примере диалога (по шагам, с анализом каждого вопроса бота)

5. **Чего мы хотим от архитектора** (требования к решению)

6. **Листинги Python кода** (MainAgent, ProblemAccumulationService, FilterDetectionService)

7. **Полную структуру БД** (PostgreSQL: services_catalog, ref_*, dialog_logs)

8. **Отладку по шаблону** (trace_report_service: что это, как работает, как помогает)

ТЗ должно быть структурированным, подробным и готовым к передаче архитектору.

---

# КОНТЕКСТ

## Система: AI-диспетчер УК "Аспект"

**Назначение:** Определить услугу из каталога по описанию проблемы пользователя

**Каналы связи:**
- Telegram бот (@KomunalkaProblemBot)
- Веб-чат (http://komunal-dom.ru/chat/)
- Голосовой интерфейс (через оператора)

**Технический стек:**
- Python 3.12, Django 6.0, asyncio
- PostgreSQL 16
- YandexGPT (Lite/Pro)
- Веб: nginx, gunicorn

**База данных:**
- Таблица `services_catalog`: ~50 услуг
- Справочники: `ref_categories`, `ref_localization`, `ref_objects`, `ref_service_types`
- Логи: `dialog_logs` (все сообщения с metadata JSONB)

---

## Архитектура микросервисов под управлением MainAgent

```
MainAgent (координатор, файл: main_agent.py, 2600+ строк)
│
├─ TagSearchService - нечеткий поиск по тегам
│  └─ Ищет услуги по keywords в тегах
│  └─ Возвращает: {service_id, service_name, confidence, source}
│
├─ SemanticSearchService - логико-семантический поиск
│  └─ Анализирует логические связи в тексте
│  └─ Возвращает: {service_id, service_name, confidence, source}
│
├─ VectorSearchService - семантический поиск по векторной базе
│  └─ Использует эмбеддинги (sentence-transformers)
│  └─ Возвращает: {service_id, service_name, confidence, source}
│
├─ FilterDetectionService - определение фильтров
│  └─ Извлекает: incident_type, location_type, category, object_description
│  └─ Вызывает LLM (AIAgentService)
│  └─ Возвращает: {incident, location, category, object, confidence}
│
├─ ProblemAccumulationService - накопление описания проблемы (txtPrb)
│  └─ Принцип: итеративное накопление из диалога
│  └─ 'привет' → txtPrb = ''
│  └─ 'у меня течет' → txtPrb = 'у пользователя течет'
│  └─ 'в зале' → txtPrb = 'у пользователя течет в зале'
│  └─ 'из трубы' → txtPrb = 'у пользователя течет из трубы в зале'
│  └─ Возвращает: {updated_problem, fields: {problem, location, source, etc.}}
│
└─ AI Orchestrator - умное объединение результатов
   └─ Запускает микросервисы параллельно
   └─ Объединяет результаты (UNION, не INTERSECTION)
   └─ Фильтрует по established_filters
   └─ Генерирует вопросы через YandexGPT
```

---

## Алгоритм работы MainAgent (воронка точности)

### ШАГ 1: ProblemAccumulationService → накопление txtPrb

```python
# ИЗВЛЕКАЕТ информацию из сообщения пользователя
accumulation_result = await self.problem_accumulator.extract_and_accumulate(
    message_text="в зале",
    current_problem="у пользователя течет",
    bot_question="Где именно?",
    dialog_history=[...]
)

# Результат:
txtPrb = "у пользователя течет в зале"
fields = {
    'problem': 'течет',
    'location': 'зал',
    'source': None,
    'category': None
}
```

### ШАГ 2: Параллельный запуск быстрых микросервисов

```python
search_tasks = []
if self.tag_search:
    search_tasks.append(self._run_tag_search(message_text))
if self.semantic_search:
    search_tasks.append(self._run_semantic_search(message_text))
if self.vector_search:
    search_tasks.append(self._run_vector_search(message_text))

search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
```

**Результат:**
```python
{
    'tag_search': {
        'candidates': [
            {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'confidence': 0.95}
        ]
    },
    'vector_search': {
        'candidates': [
            {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'confidence': 0.92},
            {'service_id': 31, 'service_name': 'Устранение течи из батареи', 'confidence': 0.75}
        ]
    }
}
```

### ШАГ 3: AI Orchestrator → объединение и фильтрация

```python
orch_result = await self._orchestrate_microservices(
    message_text=search_text,
    search_results=search_results,
    dialog_history=dialog_history,
    txtPrb=txtPrb,
    established_filters=established_filters
)
```

**Логика:**
- UNION всех кандидатов (не пересечение!)
- Дедупликация по service_id
- Повышение confidence при совпадениях от разных сервисов
- Фильтрация по established_filters

### ШАГ 4: FilterDetectionService → определение фильтров

```python
filter_result = await self.filter_detection.detect_filters(
    message_text="у меня течет в зале",
    dialog_history=[...]
)

# Результат:
filters = {
    'incident_type': 'Инцидент',
    'location_type': 'Индивидуальное',
    'category': 'Водоснабжение',
    'object_description': 'течь зал',
    'confidence': 0.85
}
```

### ШАГ 5: Генерация уточняющего вопроса

```python
ai_result = await self._generate_ai_question(
    context=context,
    dialog_history=dialog_history,
    candidates=candidates,
    established_filters=established_filters,
    txtPrb=txtPrb,
    question_type='clarification'
)

# Результат:
question = "Опишите что именно сломалось?"
```

---

## Структура услуги в БД

```sql
CREATE TABLE services_catalog (
    service_id INTEGER PRIMARY KEY,
    scenario_name VARCHAR(255) NOT NULL,          -- Название услуги
    incident_type VARCHAR(50),                    -- 'Инцидент' | 'Запрос'
    location_type VARCHAR(50),                    -- 'Индивидуальное' | 'Общедомовое'
    category VARCHAR(100),                        -- 'Водоснабжение' | 'Отопление' | ...
    object_type VARCHAR(100),                     -- 'Труба' | 'Кран' | 'Батарея' | ...
    description_for_search TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Индексы для поиска
CREATE INDEX idx_services_catalog_scenario_name_trgm
ON services_catalog USING gin(scenario_name gin_trgm_ops);
```

**Фильтры (денормализованные поля):**
- `incident_type`: 'Инцидент' (сломалось) / 'Запрос' (информация)
- `location_type`: 'Индивидуальное' (квартира) / 'Общедомовое' (подъезд)
- `category`: 'Водоснабжение', 'Отопление', 'Канализация', 'Электрика', 'Санитария'
- `object_type`: 'Труба', 'Кран', 'Батарея', 'Розетка', 'Выключатель'

---

# ПРИМЕРЫ

## Проблемный диалог (для анализа)

```
Vladimir Chernikin, [01.01.2026 22:32]
Привет

KomunalkaBot, [01.01.2026 22:32]
Здравствуйте! Опишите вашу проблему, и я попробую помочь.

Vladimir Chernikin, [01.01.2026 22:32]
у меня течет

KomunalkaBot, [01.01.2026 22:32]
(определяю локацию): Где именно произошла протечка? В квартире или в общедомовой зоне?

Vladimir Chernikin, [01.01.2026 22:32]
в зале

KomunalkaBot, [01.01.2026 22:32]
(уточняю детали): Из какого именно места течёт в зале?

Vladimir Chernikin, [01.01.2026 22:33]
из трубы

KomunalkaBot, [01.01.2026 22:33]
(определяет объект): Из какой именно трубы течёт? (горячей или холодной воды)

Vladimir Chernikin, [01.01.2026 22:33]
не понял

KomunalkaBot, [01.01.2026 22:33]
(определяет объект): Из какой именно трубы течёт? (горячей или холодной воды, отопления)

Vladimir Chernikin, [01.01.2026 22:33]
отопление

KomunalkaBot, [01.01.2026 22:33]
(определяет объект): Что именно случилось с трубой в зале?

Vladimir Chernikin, [01.01.2026 22:33]
течет

KomunalkaBot, [01.01.2026 22:33]
(фильтрую 10 кандидатов): Течёт из трубы в вашей квартире или в общедомовой системе?

Vladimir Chernikin, [01.01.2026 22:33]
я уже сказал

KomunalkaBot, [01.01.2026 22:33]
(уточняет детали): Можете уточнить, какая именно проблема возникла?

Vladimir Chernikin, [01.01.2026 22:33]
течет

KomunalkaBot, [01.01.2026 22:33]
(определяет локацию): Где именно произошла протечка?
```

---

## Текущий промпт MainAgent (для анализа)

### Шаблон промпта с параметрами

```
Ты - AI-диспетчер УК "Аспект".

══════════════════════════════════════════════════════════════════════════════
🎯 ГЛАВНАЯ ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Сформировать заявку от абонента в формате JSON:
  - timestamp: время обращения
  - telegram_user: ник пользователя
  - dialog_id: ID диалога
  - service_id: ID услуги
  - address_id: ID объекта обслуживания

Этап 1: Определить услугу (поиск в каталоге, подтверждение от пользователя)
Этап 2: Определить адрес (через AddressExtractor)
Этап 3: Вернуть JSON заявки

══════════════════════════════════════════════════════════════════════════════
🎯 ИНСТРУКЦИЯ ПО ГЕНЕРАЦИИ ВОПРОСА
══════════════════════════════════════════════════════════════════════════════

Верни уточняющий открытый вопрос который:
1. СОКРАТИТ список кандидатов до ОДНОЙ услуги
   ИЛИ
2. НАЛОЖИТ один из фильтров (Тип/Вид/Категория/Объект) на множество кандидатов

Ограничения:
- Максимальная длина: 10 слов
- Только ОДИН вопрос
- Открытый вопрос (без вариантов ответа)

❌ НЕ ПРИМЕНЯЙ:
- Двойные вопросы ("что и где?")
- Перечисления вариантов ("например, труба или батарея?")
- Закрытые вопросы (да/нет) - КРОМЕ исключения ниже
- Слово "например" и любые перечисления через него
- Внутренние термины "Инцидент/Запрос"

✅ ИСКЛЮЧЕНИЕ (закрытый вопрос РАЗРЕШЕН):
Если один кандидат имеет вероятность 90%+ → спроси: "Правильно ли я понял, что у вас [описание проблемы]?"

══════════════════════════════════════════════════════════════════════════════
📋 ТЕКУЩАЯ СИТУАЦИЯ
══════════════════════════════════════════════════════════════════════════════

[CONTEXT]  <-- Описание ситуации от пользователя

✅ УЖЕ ИЗВЕСТНО (не спрашивай повторно):
[KNOWN_INFO]  <-- Что уже извлечено из диалога

📝 ОПИСАНИЕ ПРОБЛЕМЫ (txtPrb):
[TXT_PRB]  <-- Накопленное описание проблемы

💬 ИСТОРИЯ ДИАЛОГА:
[DIALOG_HISTORY]  <-- Последние 4-6 сообщений

🔧 УСТАНОВЛЕННЫЕ ФИЛЬТРЫ (с вероятностью):
[ESTABLISHED_FILTERS]  <-- Фильтры с confidence > 0.8

📋 СПИСОК КАНДИДАТОВ:
[CANDIDATES_JSON]  <-- JSON с кандидатами (до 15 штук)

══════════════════════════════════════════════════════════════════════════════
🎯 ЗАДАЧА
══════════════════════════════════════════════════════════════════════════════

Верни ОДИН вопрос который:
- Позволит однозначно определить кандидата ИЛИ наложить фильтр
- Максимально короткий (до 10 слов)
- Открытый вопрос (без перечислений вариантов)
- Учитывает уже известную информацию
- ПРИБЛИЖАЕТ К РЕШЕНИЮ

Вопрос:
```

### Реально заполненный промпт (на примере шага #8)

**Шаг #8:** Пользователь ответил "отопление"

```
Ты - AI-диспетчер УК "Аспект".

🎯 ГЛАВНАЯ ЗАДАЧА
Сформировать заявку от абонента...

📋 ТЕКУЩАЯ СИТУАЦИЯ
Пользователь написал: отопление

✅ УЖЕ ИЗВЕСТНО (не спрашивай повторно):
- Проблема: течет
- Локация: зал
- Источник: труба
- Категория: Отопление (confidence: 95%)
- Вид: Индивидуальное (confidence: 95%)
- Тип: Инцидент (confidence: 90%)

📝 ОПИСАНИЕ ПРОБЛЕМЫ (txtPrb):
у пользователя течет из трубы в зале

💬 ИСТОРИЯ ДИАЛОГА:
Пользователь: у меня течет
Бот: Где именно произошла протечка? В квартире или в общедомовой зоне?
Пользователь: в зале
Бот: Из какого именно места течёт в зале?
Пользователь: из трубы
Бот: Из какой именно трубы течёт? (горячей или холодной воды)
Пользователь: не понял
Бот: Из какой именно трубы течёт? (горячей или холодной воды, отопления)
Пользователь: отопление

🔧 УСТАНОВЛЕННЫЕ ФИЛЬТРЫ (с вероятностью):
- location: Индивидуальное (95%)
- category: Отопление (95%)
- incident: Инцидент (90%)
- object: труба (85%)

📋 СПИСОК КАНДИДАТОВ:
```json
[
  {
    "КодУслуги": 25,
    "Наименование": "Прорыв труб в квартире",
    "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Водоснабжение", "Объект": "Труба"}
  },
  {
    "КодУслуги": 31,
    "Наименование": "Устранение течи из батареи отопления",
    "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Отопление", "Объект": "Батарея"}
  },
  {
    "КодУслуги": 33,
    "Наименование": "Течь из трубы отопления в квартире",
    "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Отопление", "Объект": "Труба"}
  }
]
```

🎯 ЗАДАЧА
Верни ОДИН вопрос который:
- Позволит однозначно определить кандидата ИЛИ наложить фильтр
- Учитывает уже известную информацию
- ПРИБЛИЖАЕТ К РЕШЕНИЮ

❌ НЕ ПРИМЕНЯЙ:
- Двойные вопросы
- Закрытые вопросы (да/нет)
- Перечисления вариантов
- Спрашивать то, что УЖЕ известно (локация=зал, объект=труба, категория=отопление)

Вопрос:
```

**Ожидаемый вопрос:**
```
Что именно случилось с трубой отопления в зале?
```

**Реальный ответ LLM (ПРОБЛЕМА!):**
```
Что именно случилось с трубой в зале?
```

---

# ПРОБЛЕМЫ В ТЕКУЩЕМ ПРОМТЕ (на примере диалога)

## Проблема 1: LLM игнорирует блок "УЖЕ ИЗВЕСТНО"

**Шаг #9:**
- txtPrb: "у пользователя течет из трубы отопления в зале"
- established_filters: location=95%, category=95%, incident=90%
- Бот спрашивает: "Где именно произошла протечка?"

**Причина:** Блок "УЖЕ ИЗВЕСТНО" находится в середине промта, LLM "забывает" его к концу

---

## Проблема 2: Двойные вопросы через "или"

**Шаг #2:**
- Пользователь: "у меня течет"
- Бот: "Где именно произошла протечка? В квартире или в общедомовой зоне?"

**Проблема:** Двойной вопрос ("что" + "где" через "или")

**Причина:** Промт запрещает двойные вопросы, но не содержит позитивных примеров как спрашивать правильно

---

## Проблема 3: Закрытые вопросы с перечислением

**Шаг #4:**
- Пользователь: "из трубы"
- Бот: "Из какой именно трубы течёт? (горячей или холодной воды)"

**Проблема:** Закрытый вопрос с перечислением вариантов в скобках

**Причина:** LLM пытается "помочь" пользователю, но нарушает промт

---

## Проблема 4: Не учитывает txtPrb

**Шаг #6:**
- txtPrb: "у пользователя течет из трубы отопления в зале"
- Бот спрашивает: "Что именно случилось с трубой в зале?"

**Проблема:** txtPrb УЖЕ содержит "течет", но вопрос спрашивает "что именно?"

**Причина:** LLM не анализирует txtPrb как единое описание

---

## Проблема 5: Не реагирует на "я уже сказал"

**Шаг #8:**
- Пользователь: "я уже сказал"
- Бот: "Можете уточнить, какая именно проблема возникла?"

**Проблема:** Бот не меняет стратегию при раздражении пользователя

**Причина:** Нет детектора раздражения и обработки этого случая

---

## Проблема 6: Не использует established_filters

**Шаг #7:**
- established_filters: location=Индивидуальное (95%)
- Бот спрашивает: "Течёт из трубы в вашей квартире или в общедомовой системе?"

**Проблема:** Бот игнорирует фильтр с confidence > 0.8

**Причина:** Нет проверки: "если established_filters[location] > 0.8, НЕ спрашивать локацию"

---

## Проблема 7: Нет проверки соответствия локации

**Шаг #3:**
- Пользователь: "в зале"
- "зал" явно = Индивидуальное (комната в квартире)
- Бот на шаге #2 спрашивает: "В квартире или в общедомовой зоне?"

**Проблема:** Бот не понимает, что "зал" → "Индивидуальное"

**Причина:** Нет логики: "если локация = зал/ванная/кухня → location=Индивидуальное"

---

# ЧТО ХОЧУ ОТ АРХИТЕКТОРА

## Основная задача

Предложить решение (ПРОМПТ + ИЗМЕНЕНИЯ В КОДЕ) которое устранит проблемы 1-7.

## Требования к решению

### 1. Улучшенный промт MainAgent

**Структура:**
```
⚠️ КРИТИЧЕСКИ ВАЖНО: УЖЕ ИЗВЕСТНО
txtPrb: "[TXT_PRB]"
established_filters: [ESTABLISHED_FILTERS с confidence > 0.8]

🎯 ЗАДАЧА (одной строкой)

📋 КАНДИДАТЫ (сразу JSON)

💬 ИСТОРИЯ (последние 2-3 сообщения)

❌ ЗАПРЕЩЕННЫЕ ПАТТЕРНЫ (с примерами)
✅ РАЗРЕШЕННЫЕ ПАТТЕРНЫ (с примерами)

Вопрос:
```

**Обоснование:** Почему новая структура лучше текущей

### 2. Изменения в коде Python

**Обязательные методы:**

#### 2.1. LLM-валидация сгенерированного вопроса
```python
async def _llm_validate_question_redundancy(
    self, question: str, txtPrb: str, established_filters: Dict
) -> Dict:
    """
    LLM-валидация: спрашивает ли вопрос то, что УЖЕ известно?

    Returns:
        Dict: {
            'is_redundant': bool,
            'reason': str,
            'suggested_fix': str | None
        }
    """
    # Промт для LLM
    # Проверка: спрашивает ли вопрос то, что в txtPrb
    # Возврат is_redundant + suggested_fix
```

#### 2.2. Детектор раздражения ("я уже сказал")
```python
def _detect_user_frustration(
    self, message_text: str, dialog_history: List[Dict]
) -> bool:
    """
    Детектирует раздражение пользователя

    Returns:
        bool: True если пользователь раздражен
    """
    # Проверка keywords: ['я уже сказал', 'уже отвечал', ...]
    # Проверка: 3+ одинаковых ответа подряд
```

#### 2.3. Pre-check известной информации
```python
async def _precheck_known_info(
    self, txtPrb: str, established_filters: Dict
) -> Dict:
    """
    Извлекает из txtPrb: location, object, problem, category

    Returns:
        Dict: {
            'known_location': str | None,
            'known_object': str | None,
            'should_ask_location': bool,
            'should_ask_object': bool
        }
    """
    # LLM анализ txtPrb
    # Возвращает что известно и что спросить
```

### 3. Реальный пример

На шаге #8 диалога ("отопление") показать:
- Как выглядит УЛУЧШЕННЫЙ промпт
- Какой вопрос сгенерирует LLM с этим промптом
- Почему этот вопрос ЛУЧШЕ текущего

### 4. План тестирования

- Тест 1: txtPrb="течет из трубы отопления в зале" → вопрос НЕ "где?"
- Тест 2: "я уже сказал" → детектор frustrated=True
- Тест 3: location=95% → вопрос НЕ "какая локация?"
- Использование trace_report_service для отладки

---

# ЛИСТИНГИ PYTHON КОДА

## MainAgent (main_agent.py, 2600+ строк)

### Инициализация
```python
class MainAgent:
    def __init__(self):
        self.tag_search = None
        self.semantic_search = None
        self.vector_search = None
        self.ai_agent = None
        self.filter_detection = None  # FilterDetectionService
        self.problem_accumulator = None  # ProblemAccumulationService
        self.confidence_threshold = 0.75

        # Кэш фильтров из БД
        self._categories_cache = None
        self._objects_cache = None
```

### Основной метод
```python
async def process_service_detection(
    self, message_text: str, user_context: Dict = None
) -> Dict:
    """
    Основной метод определения услуги через воронку точности

    Returns:
        Dict: {
            'status': 'SUCCESS' | 'AMBIGUOUS' | 'ERROR',
            'service_id': int | None,
            'service_name': str | None,
            'message': str,
            'candidates': List[Dict],
            '_metadata': Dict
        }
    """
    # 1. ProblemAccumulation → txtPrb
    # 2. Параллельный запуск микросервисов
    # 3. AI Orchestrator → объединение
    # 4. FilterDetection → фильтры
    # 5. Генерация вопроса
```

### Генерация вопроса
```python
async def _generate_ai_question(
    self,
    context: str,
    dialog_history: List[Dict] = None,
    candidates: List[Dict] = None,
    established_filters: Dict = None,
    txtPrb: str = None,
    question_type: str = "clarification"
) -> Dict[str, str]:
    """
    Универсальный метод для генерации вопросов через AI

    Returns:
        Dict: {
            'question': str,
            'prompt': str,
            'response': str,
            'model': str,
            'usage': Dict
        }
    """
    # Формирует промт
    # Вызывает YandexGPT
    # Post-processing: _fix_double_questions, _validate_question_not_redundant
```

### Пост-валидация
```python
def _validate_question_not_redundant(
    self, question: str, txtPrb: str = None, established_filters: Dict = None
) -> str:
    """
    ПРОВЕРЯЕТ, что вопрос НЕ спрашивает то, что УЖЕ известно

    ⚠️ КРИТИЧЕСКИ ВАЖНО: Этот метод DETECTS но НЕ FIXES все проблемы!
    Проверяет только KEYWORDS, не семантику!
    """
    # ПРОВЕРКА 1: txtPrb содержит локацию, а вопрос "где?"
    # ПРОВЕРКА 2: established_filters с high confidence
```

---

## ProblemAccumulationService (problem_accumulation_service.py)

```python
class ProblemAccumulationService:
    """
    Микросервис для итеративного накопления описания проблемы

    Принцип работы:
    - 'привет' → txtPrb = ''
    - 'у меня течет' → txtPrb = 'у пользователя течет'
    - 'в зале' → txtPrb = 'у пользователя течет в зале'
    - 'из трубы' → txtPrb = 'у пользователя течет из трубы в зале'
    """

    async def extract_and_accumulate(
        self,
        message_text: str,
        current_problem: str,
        bot_question: str = None,
        dialog_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Извлекает информацию из сообщения и накапливает описание

        Returns:
            {
                'updated_problem': str,
                'is_meaningful': bool,
                'fields': {
                    'problem': str | None,
                    'location': str | None,
                    'source': str | None,
                    'category': str | None
                }
            }
        """
        # Формирует промт для LLM
        # Вызывает LLM
        # Парсит JSON
```

---

## FilterDetectionService (filter_detection_service.py)

```python
class FilterDetectionService:
    """
    Микросервис определения фильтров через LLM

    Определяет:
    - incident_type: Инцидент или Запрос
    - location_type: Индивидуальное или Общедомовое
    - category: категория проблемы
    - object_description: описание объекта
    """

    def __init__(self, ai_agent_service=None):
        self.ai_agent = ai_agent_service
        self.categories_list = []
        self.objects_examples = []
        self._load_reference_data_from_db()  # Загружает из БД!

    async def detect_filters(
        self, message_text: str, dialog_history: List[Dict] = None
    ) -> Dict:
        """
        Определяет фильтры из сообщения и истории

        Returns:
            {
                'status': 'success',
                'filters': {
                    'incident_type': 'Инцидент',
                    'location_type': 'Индивидуальное',
                    'category': 'Водоснабжение',
                    'object_description': 'течь зал'
                },
                'confidence': 0.85
            }
        """
```

---

# ПОЛНАЯ СТРУКТУРА БД

## Основная таблица: services_catalog

```sql
CREATE TABLE services_catalog (
    service_id INTEGER PRIMARY KEY DEFAULT nextval('services_catalog_service_id_seq'::regclass),

    -- Основные поля
    scenario_id VARCHAR(20) NOT NULL UNIQUE,
    scenario_name VARCHAR(255) NOT NULL,
    description_for_search TEXT,
    is_active BOOLEAN DEFAULT TRUE,

    -- Внешние ключи на справочники
    type_id SMALLINT NOT NULL REFERENCES ref_service_types(type_id),
    kind_id SMALLINT NOT NULL REFERENCES ref_service_kinds(kind_id),
    localization_id SMALLINT NOT NULL REFERENCES ref_localization(localization_id),
    category_id SMALLINT NOT NULL REFERENCES ref_categories(category_id),
    object_id SMALLINT NOT NULL REFERENCES ref_objects(object_id),
    payment_id SMALLINT NOT NULL REFERENCES ref_payment_status(payment_id),
    route_id SMALLINT NOT NULL REFERENCES ref_routes(route_id),
    urgency_id SMALLINT NOT NULL REFERENCES ref_urgency(urgency_id),

    -- Денормализованные поля (НОВАЯ система - используются в промте!)
    incident_type VARCHAR(50),       -- 'Инцидент' | 'Запрос'
    category VARCHAR(100),           -- 'Водоснабжение' | 'Отопление' | ...
    location_type VARCHAR(100),      -- 'Индивидуальное' | 'Общедомовое'

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Индексы для поиска
CREATE INDEX idx_services_catalog_active ON services_catalog(is_active);
CREATE INDEX idx_services_catalog_scenario_name_trgm ON services_catalog USING gin(scenario_name gin_trgm_ops);
```

## Справочники

```sql
-- Категории (13 штук)
CREATE TABLE ref_categories (
    category_id SMALLINT PRIMARY KEY,
    category_code VARCHAR(50) NOT NULL UNIQUE,
    category_name VARCHAR(255) NOT NULL
);
-- Данные: Водоснабжение, Отопление, Канализация, Электрика, Санитария, etc.

-- Локации
CREATE TABLE ref_localization (
    localization_id SMALLINT PRIMARY KEY,
    localization_code VARCHAR(50) NOT NULL UNIQUE,
    localization_name VARCHAR(255) NOT NULL
);

-- Типы услуг
CREATE TABLE ref_service_types (
    type_id SMALLINT PRIMARY KEY,
    type_code VARCHAR(50) NOT NULL UNIQUE,
    type_name VARCHAR(255) NOT NULL
);

-- Объекты
CREATE TABLE ref_objects (
    object_id SMALLINT PRIMARY KEY,
    category_id SMALLINT REFERENCES ref_categories(category_id),
    object_code VARCHAR(50) NOT NULL UNIQUE,
    object_name VARCHAR(255) NOT NULL
);
```

## Логи диалогов

```sql
CREATE TABLE dialog_logs (
    id INTEGER PRIMARY KEY DEFAULT nextval('dialog_logs_id_seq'::regclass),
    dialog_id UUID,
    user_id INTEGER NOT NULL,
    message_type VARCHAR(50) NOT NULL,  -- 'inbound' | 'outbound'
    message_content TEXT NOT NULL,
    processing_stage VARCHAR(100),
    confidence_score NUMERIC(5,4),
    service_detected_id INTEGER REFERENCES services_catalog(service_id),
    address_extracted JSONB,
    llm_provider VARCHAR(100),
    llm_model VARCHAR(100),
    tokens_used INTEGER,
    cost_rub NUMERIC(10,6),
    timestamp TIMESTAMPTZ DEFAULT now(),
    metadata JSONB
);

CREATE INDEX idx_dialog_logs_dialog_id ON dialog_logs(dialog_id);
CREATE INDEX idx_dialog_logs_user_id ON dialog_logs(user_id);
```

---

# ОТЛАДКА ПО ШАБЛОНУ

## Что такое trace_report_service?

**Файл:** `/var/www/komunal-dom_ru/trace_report_service.py`

**Назначение:** Микросервис для генерации детальных отчетов трассировки диалогов по фиксированному шаблону.

**Принцип работы:**
1. После каждого сообщения сохраняется полный отчет в `/tmp/_tras_diag_ГГГГММДД_ЧЧММСС.md`
2. Отчет содержит ВСЮ информацию: входные параметры, txtPrb, фильтры, кандидатов, промты LLM, ответы
3. Архитектор анализирует отчет и находит проблему

## Шаблон отчета

```markdown
================================================================================
ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА (улучшенный шаблон v2.0 - 2025-12-28)
================================================================================
Session ID: telegram_1049252307_20251228_133000
Всего сообщений: 6

================================================================================
ИСТОРИЯ txtPrb (накопление описания проблемы)
================================================================================

#1: (нет значимой информации)
#2: у пользователя течет
#3: у пользователя течет в зале
#4: у пользователя течет из трубы в зале
#5: у пользователя течет из трубы отопления в зале

================================================================================
ДЕТАЛЬНАЯ ТРАССИРОВКА ПО СООБЩЕНИЯМ
================================================================================

СООБЩЕНИЕ #7
ID: 1267
Направление: inbound
Текст: "отопление"

┌─── АНАЛИЗ СООБЩЕНИЯ ───┐
│                        │
├─ ЗНАЧИМАЯ ИНФОРМАЦИЯ:
✅ Категория: "отопление"
✅ Объект: "труба" (из контекста)
│
└─ ЗАКЛЮЧЕНИЕ:
✅ Сообщение содержит ЗНАЧИМУЮ информацию

txtPrb после обработки: "у пользователя течет из трубы отопления в зале"

┌─── РЕЗУЛЬТАТЫ МИКРОСЕРВИСОВ ───┐
│                                │
├─ TagSearchService:
│  (нет кандидатов)
│
├─ VectorSearchService:
│  ID:33 | Течь из трубы отопления в квартире | 98.00%
│
└─ AIAgentService:
   (не вызван)

─── ПЕРЕСЕЧЕНИЕ ───
Общий кандидат: 1
ID:33 | Течь из трубы отопления | 98.00%

┌─── ФИЛЬТРЫ (FilterDetectionService) ───┐
│                                         │
├─ ЗАПРОС К LLM:
"Извлеки фильтры из сообщения: 'отопление'"
│
├─ ОТВЕТ LLM:
{
  "category": "Отопление",
  "incident": "Инцидент"
}
│
└─ ФАКТИЧЕСКИЕ ФИЛЬТРЫ:
category = Отопление (confidence: 95%)
incident = Инцидент (confidence: 90%)

🔧 УСТАНОВЛЕННЫЕ ФИЛЬТРЫ:
- location: Индивидуальное (95%)
- category: Отопление (95%)
- incident: Инцидент (90%)
- object: труба (85%)

📋 СПИСОК КАНДИДАТОВ:
- ID:33 | Течь из трубы отопления в квартире | 98% (Отопление, Индивидуальное)

METADATA:
service_detection:
  status: SUCCESS
  message: "Правильно ли я понял, что у вас течет из трубы отопления в зале?"
  candidates:
    - ID:33
      service_name: "Течь из трубы отопления в квартире"
      confidence: 98.00%

ОТВЕТ БОТА:
"Правильно ли я понял, что у вас течет из трубы отопления в зале?"
```

## Как использовать

### Генерация отчета
```bash
# По session_id
python trace_report_service.py --session-id telegram_1049252307_20251228_133000

# По telegram_user_id
python trace_report_service.py --telegram-user-id 1049252307

# Просмотр последнего
cat /tmp/_tras_diag_$(ls -t /tmp/_tras_diag_*.md | head -1 | xargs basename)
```

### Анализ отчета

**Пример проблемы:**
```
СООБЩЕНИЕ #9
txtPrb: "у пользователя течет из трубы отопления в зале"
established_filters: location=95%, category=95%
candidates: ID:33 | Течь из трубы отопления | 98%

ОТВЕТ БОТА: "Течёт из трубы в вашей квартире или в общедомовой системе?"
```

**Анализ:**
- Бот игнорирует txtPrb (содержит "зале" → Индивидуальное)
- Бот игнорирует established_filters (location=95%)
- Есть кандидат ID:33 с 98% confidence!

**Вывод:** Нужно добавить в промт:
```
⚠️ КРИТИЧЕСКИ ВАЖНО: НЕ спрашивай локацию если:
- txtPrb содержит "зал/ванная/кухня/спальня" → location=Индивидуальное
- established_filters['location'] > 0.8 → localization известна
```

---

# ОГРАНИЧЕНИЯ

## Технические
- **Модель:** YandexGPT (Lite/Pro)
- **Макс. длина промта:** ~4000 токенов
- **Python:** 3.12, Django 6.0, asyncio
- **БД:** PostgreSQL 16

## Бизнес
- **Интерфейс:** Голосовой (без кнопок)
- **Стиль:** Прямой, деловой, БЕЗ эмодзи
- **Пользователь:** Не технический

## Диалога
- **Ответы:** Краткие ("да", "нет", "отопление")
- **Раздражение:** "я уже сказал" - возможен
- **Длина вопроса:** Max 10 слов

---

# ВЫХОДНОЙ ФОРМАТ

Создай файл `TZ_MAINAGENT_PROMPT_ARCHITECT_V2.md` со следующей структурой:

1. **Анализ текущего подхода** (5-7 проблем в промте, 3-5 в коде)
2. **Улучшенная архитектура** (промт + изменения в коде)
3. **Шаблон улучшенного промта** (с параметрами `[PARAMETER]`)
4. **Реальный пример** (заполненный шаблон на шаге #8)
5. **План внедрения** (что изменить в коде, как тестировать)
6. **Критерии успеха** (метрики: % диалогов с "я уже сказал" < 5%)

ТЗ должно быть развернутым, с примерами, объяснениями и готовым к передаче архитектору.

---

**Важно:** Ты создаешь ТЗ ДЛЯ АРХИТЕКТОРА, а не выполняешь архитектуру сам. ТЗ должно быть настолько подробным, чтобы архитектор мог сразу начать работу, не задавая дополнительных вопросов.
