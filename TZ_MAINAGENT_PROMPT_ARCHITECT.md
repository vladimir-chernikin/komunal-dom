# ТЗ НА МОДЕРНИЗАЦИЮ ПРОМТА MAINAGENT И АЛГОРИТМА ОПРЕДЕЛЕНИЯ УСЛУГ

**Дата:** 2026-01-01
**Проект:** komunal-dom.ru
**Назначение:** Для исследования нейросетью архитектором

---

## 1. ОБЩАЯ РОЛЬ

**Ты:** Senior AI Architect и Software Architect, специализирующийся на:
- Prompt Engineering для LLM (YandexGPT, GPT, Claude)
- Диалоговых системах и чат-ботах
- Python/Django разработке
- Проектировании баз данных
- Микросервисной архитектуре

**Контекст проекта:**
- Система: AI-диспетчер управляющей компании (УК "Аспект")
- Каналы связи: Telegram бот, веб-чат, голосовой интерфейс (через оператора)
- Задача: Определить услугу из каталога по описанию проблемы пользователя
- Каталог услуг: ~50+ услуг (Водоснабжение, Отопление, Канализация, Электрика и т.д.)
- База: PostgreSQL 16 (таблица `services_catalog` + справочники)
- Стек: Python 3.12, Django 6.0, asyncio

**Проблема:** Бот задает лишние вопросы, раздражает пользователя, циклится ("я уже сказал"), не понимает накопленную информацию из диалога, НЕ ИСПОЛЬЗУЕТ txtPrb для фильтрации вопросов.

---

## 2. ИНСТРУКЦИЯ АГЕНТУ

Твоя задача:
1. Проанализировать текущий промт MainAgent и алгоритм определения услуг
2. Выявить проблемы в промте (почему бот задает лишние вопросы?)
3. Предложить улучшенную архитектуру промта
4. Дать конкретный шаблон промта с параметрами в скобках `[PARAMETER]`
5. Показать реальный пример заполненного промта на основе реального диалога
6. Объяснить все проблемы текущего подхода

---

## 3. КОНТЕКСТ: АРХИТЕКТУРА СИСТЕМЫ

### 3.1. Микросервисы под управлением MainAgent

```
MainAgent (координатор)
├─ TagSearchService - нечеткий поиск по тегам
├─ SemanticSearchService - логико-семантический поиск
├─ VectorSearchService - семантический поиск по векторной базе
├─ FilterDetectionService - определение фильтров (location, category, incident)
├─ ProblemAccumulationService - накопление описания проблемы (txtPrb)
└─ AI Orchestrator - умное объединение результатов через YandexGPT
```

### 3.2. Алгоритм работы ворнки точности

**ШАГ 1: Параллельный поиск**
```python
# Запускаем 3 быстрых микросервиса параллельно
search_tasks = [
    tag_search.search(message_text),
    semantic_search.search(message_text),
    vector_search.search(message_text)
]
results = await asyncio.gather(*search_tasks)
```

**ШАГ 2: Объединение результатов (UNION)**
```python
# Собираем всех кандидатов с приоритетами
all_candidates = []
for result in results:
    for candidate in result['candidates']:
        all_candidates.append({
            'service_id': candidate['id'],
            'service_name': candidate['name'],
            'confidence': candidate['confidence'],
            'source': result['method']
        })

# Дедупликация
unique_candidates = deduplicate(all_candidates)
```

**ШАГ 3: AI Orchestrator**
```python
if len(unique_candidates) == 1:
    return SUCCESS(confirmed=True)
elif len(unique_candidates) <= 10:
    return await ai_clarification(unique_candidates, dialog_history)
else:
    return await ask_what_happened(dialog_history)
```

**ШАГ 4: Накопление информации (txtPrb)**
```python
# ProblemAccumulationService накапливает описание
txtPrb = "у пользователя течет из батареи (отопление) в зале постоянно"

# Извлекает фильтры с весами
established_filters = {
    'location': {'value': 'Индивидуальное', 'confidence': 0.95},
    'category': {'value': 'Отопление', 'confidence': 0.95},
    'incident': {'value': 'Инцидент', 'confidence': 0.90}
}
```

### 3.3. Структура услуги в БД

```sql
CREATE TABLE services_catalog (
    service_id INT PRIMARY KEY,
    scenario_name VARCHAR(255),      -- Название услуги
    incident_type VARCHAR(50),       -- Инцидент/Запрос
    location_type VARCHAR(50),       -- Индивидуальное/Общедомовое
    category VARCHAR(100),           -- Водоснабжение/Отопление/...
    object_type VARCHAR(100),        -- Труба/Кран/Батарея/...
    tags TEXT[],                     -- Теги для поиска
    is_active BOOLEAN
);
```

### 3.4. Фильтры и их значения

**Location (Вид):**
- `Индивидуальное` = в квартире (ванная, зал, кухня, спальня)
- `Общедомовое` = подъезд, улица, чердак, подвал

**Incident (Тип):**
- `Инцидент` = сломалось, течет, угроза имуществу
- `Запрос` = нужно выполнить работу, НЕТ угрозы

**Category (Категория):**
- `Водоснабжение`, `Отопление`, `Канализация`, `Электрика`, `Сантехника`

**Object (Объект):**
- `Труба`, `Кран`, `Батарея`, `Розетка`, `Выключатель`

---

## 4. ТЕКУЩИЙ ПРОМТ MAINAGENT

### 4.1. ШАБЛОН ПРОМТА (с параметрами в скобках)

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
- Ответ должен приблизить к однозначному определению услуги

❌ НЕ ПРИМЕНЯЙ:
- Двойные вопросы ("что и где?")
- Перечисления вариантов ("например, труба или батарея?")
- Закрытые вопросы (да/нет) - КРОМЕ исключения ниже
- Слово "например" и любые перечисления через него
- Внутренние термины "Инцидент/Запрос" - говори по-человечески

✅ ИСКЛЮЧЕНИЕ (закрытый вопрос РАЗРЕШЕН):
Если один кандидат имеет вероятность 90%+ → спроси: "Правильно ли я понял, что у вас [описание проблемы]?"

══════════════════════════════════════════════════════════════════════════════
🔄 АЛГОРИТМ ПОИСКА УСЛУГИ
══════════════════════════════════════════════════════════════════════════════

1. Анализируй историю диалога в блоке [💬 ИСТОРИЯ ДИАЛОГА]
2. Если можешь однозначно определить услугу (вероятность 90%+):
   → Задай вопрос: "Правильно ли я понял, что у вас [описание]?"
3. Если невозможно однозначно определить:
   → Задай уточняющий вопрос который отфильтрует большинство кандидатов
   → Ответ пользователя позволит установить фильтр для следующего этапа
4. Повторяй пока не будет подтверждение услуги (90%+)

══════════════════════════════════════════════════════════════════════════════
📊 КАК РАБОТАЮТ ФИЛЬТРЫ
══════════════════════════════════════════════════════════════════════════════

Фильтры сокращают список кандидатов:

- Тип (Инцидент/Запрос):
  * Инцидент = сломалось, не работает, угроза жизни/здоровью/имуществу
  * Запрос = нужно выполнить работу, НЕТ угрозы

- Вид (Индивидуальное/Общедомовое):
  * Индивидуальное = проблема в квартире (ванная, зал, кухня, спальня)
  * Общедомовое = проблема в подъезде, на улице
  Варианты: [LOCATION_TYPES]

- Категория: [CATEGORIES]

- Объект: [OBJECTS]

Стратегия: задавай вопросы чтобы установить фильтры и сократить список кандидатов.

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

### 4.2. РЕАЛЬНЫЙ ПРИМЕР ЗАПОЛНЕННОГО ПРОМТА

**Диалог:**
```
Vladimir Chernikin: Привет
KomunalkaBot: Здравствуйте! Опишите вашу проблему, и я попробую помочь.

Vladimir Chernikin: у меня течет
KomunalkaBot: (определяю локацию): Где именно произошла протечка? В квартире или в общедомовой зоне?

Vladimir Chernikin: в зале
KomunalkaBot: (уточняю детали): Из какого именно места течёт в зале?

Vladimir Chernikin: из трубы
KomunalkaBot: (определяет объект): Из какой именно трубы течёт? (горячей или холодной воды)

Vladimir Chernikin: не понял
KomunalkaBot: (определяет объект): Из какой именно трубы течёт? (горячей или холодной воды, отопления)

Vladimir Chernikin: отопление
KomunalkaBot: (определяет объект): Что именно случилось с трубой в зале?

Vladimir Chernikin: течет
KomunalkaBot: (фильтрует 10 кандидатов): Течёт из трубы в вашей квартире или в общедомовой системе?

Vladimir Chernikin: я уже сказал
KomunalkaBot: (уточняет детали): Можете уточнить, какая именно проблема возникла?

Vladimir Chernikin: течет
KomunalkaBot: (определяет локацию): Где именно произошла протечка?
```

**Заполненный промт на шаге 8 (пользователь: "отопление"):**

```
Ты - AI-диспетчер УК "Аспект".

🎯 ГЛАВНАЯ ЗАДАЧА
Сформировать заявку от абонента в формате JSON...

🎯 ИНСТРУКЦИЯ ПО ГЕНЕРАЦИИ ВОПРОСА
Верни уточняющий открытый вопрос который:
1. СОКРАТИТ список кандидатов до ОДНОЙ услуги
...

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

**Ожидаемый ответ:**
```
Что именно случилось с трубой отопления в зале?
```

**Реальный ответ LLM (ПРОБЛЕМА!):**
```
Что именно случилось с трубой в зале?
```

---

## 5. ПРОБЛЕМЫ В ТЕКУЩЕМ ПОДХОДЕ (на примере диалога)

### 5.1. Анализ диалога по шагам

| Шаг | Пользователь | Бот | txtPrb | Проблема |
|-----|--------------|-----|--------|----------|
| 1 | "привет" | "Здравствуйте! Опишите вашу проблему..." | (пусто) | ✅ OK |
| 2 | "у меня течет" | "Где именно произошла протечка? В квартире или в общедомовой зоне?" | "у пользователя течет" | ⚠️ ДВОЯКОЙ ВОПРОС (что+где через "или") |
| 3 | "в зале" | "Из какого именно места течёт в зале?" | "у пользователя течет в зале" | ❌ НЕИЗВЕСТНО что именно течет, но спрашивает "из какого места"? |
| 4 | "из трубы" | "Из какой именно трубы течёт? (горячей или холодной воды)" | "у пользователя течет из трубы в зале" | ❌ Закрытый вопрос с перечислением |
| 5 | "не понял" | "Из какой именно трубы течёт? (горячей или холодной воды, отопления)" | (без изменений) | ❌ ПОВТОР вопроса с добавлением вариантов |
| 6 | "отопление" | "Что именно случилось с трубой в зале?" | "у пользователя течет из трубы отопления в зале" | ❌ НЕ УЧИТЫВАЕТ, ЧТО УЖЕ ИЗВЕСТНО "течет" |
| 7 | "течет" | "Течёт из трубы в вашей квартире или в общедомовой системе?" | (без изменений) | ❌ ПОВТОРНОЕ уточнение локации (УЖЕ ИЗВЕСТНО!) |
| 8 | "я уже сказал" | "Можете уточнить, какая именно проблема возникла?" | (без изменений) | ❌ НЕ РЕАГИРУЕТ на раздражение пользователя |
| 9 | "течет" | "Где именно произошла протечка?" | (без изменений) | ❌ ЦИКЛ: снова спрашивает локацию |

### 5.2. Критические проблемы промта

**ПРОБЛЕМА 1: LLM игнорирует блок "УЖЕ ИЗВЕСТНО"**
- Промт явно указывает: "✅ УЖЕ ИЗВЕСТНО (не спрашивай повторно)"
- LLM ВСЕ РАВНО спрашивает: "Где именно произошла протечка?" (шаг 9)
- Причина: Блок "УЖЕ ИЗВЕСТНО" находится ВЫШЕ в промте, а кандидаты и задача НИЖЕ

**ПРОБЛЕМА 2: Двойные вопросы через "или"**
- Шаг 2: "В квартире или в общедомовой зоне?"
- Промт запрещает: "❌ НЕ ПРИМЕНЯЙ: Двойные вопросы"
- LLM игнорирует запрет
- Причина: Промт не содержит ПОЗИТИВНОГО примера как спрашивать локацию

**ПРОБЛЕМА 3: Закрытые вопросы с перечислением**
- Шаг 4: "(горячей или холодной воды)"
- Шаг 5: "(горячей или холодной воды, отопления)"
- Промт запрещает: "❌ НЕ ПРИМЕНЯЙ: Перечисления вариантов"
- LLM добавляет перечисление в скобках
- Причина: LLM пытается "помочь" пользователю, но violates промпт

**ПРОБЛЕМА 4: Не учитывает txtPrb**
- txtPrb на шаге 6: "у пользователя течет из трубы отопления в зале"
- Бот спрашивает: "Что именно случилось с трубой в зале?"
- txtPrb УЖЕ СОДЕРЖИТ "течет", но вопрос спрашивает "что именно?"
- Причина: LLM не анализирует txtPrb как единое описание

**ПРОБЛЕМА 5: Не реагирует на "я уже сказал"**
- Пользователь явно раздражен: "я уже сказал"
- Бот продолжает задавать вопросы по алгоритму
- Причина: Нет логики обработки повторяющихся ответов

**ПРОБЛЕМА 6: Нет уточнения деталей**
- На шаге 7 известно: "течет из трубы отопления в зале"
- Локация: Индивидуальное (зал = комната в квартире)
- Категория: Отопление
- Объект: Труба
- Инцидент: Течет
- Но бот спрашивает: "Течёт из трубы в вашей квартире или в общедомовой системе?"
- Причина: LLM не проверяет, что "зал" = "Индивидуальное"

**ПРОБЛЕМА 7: Низкая приоритетность блока "УЖЕ ИЗВЕСТНО"**
- В промте блок "УЖЕ ИЗВЕСТНО" находится в середине
- После него идут еще 4 блока (История, Фильтры, Кандидаты, Задача)
- LLM "забывает" про "УЖЕ ИЗВЕСТНО" к концу промта

### 5.3. Архитектурные проблемы

**1. txtPrb НЕ используется для фильтрации**
- txtPrb накапливает описание проблемы
- Но LLM не использует txtPrb для проверки что УЖЕ известно
- Нужен явный блок: "⚠️ txtPrb СОДЕРЖИТ: [описание]. НЕ спрашивай то, что там есть."

**2. Нет валидации冗антности (redundancy)**
- Post-processing `_validate_question_not_redundant()` проверяет только keywords
- Нет семантической проверки: спрашивает ли LLM то, что уже в txtPrb
- Нужна LLM-валидация сгенерированного вопроса

**3. Нет обработки повторяющихся ответов**
- Если пользователь отвечает "я уже сказал" - бот должен МЕНЯТЬ СТРАТЕГИЮ
- Текущая логика: детектирует повтор ответов пользователя (строки 366-420)
- Но меняет вопрос только при повторяющихся ответах, а не при "я уже сказал"

**4. established_filters с низким confidence**
- Фильтр "object" имеет confidence 85% (труба)
- Бот спрашивает "Что именно?" - игнорируя фильтр
- Нужен порог: если confidence > 0.8, НЕ спрашивать

**5. Нет проверки соответствия локации**
- "зал" явно = Индивидуальное (комната в квартире)
- Бот спрашивает "квартира или общедомовое?" - игнорируя это
- Нужна логика: если локация = "зал/ванная/кухня/спальня" → location=Индивидуальное (автоматически)

---

## 6. ЧТО ХОЧУ ОТ АРХИТЕКТОРА

### 6.1. Предложить улучшенную архитектуру промта

**Требования:**
1. Перестроить структуру промта так, чтобы:
   - Блок "УЖЕ ИЗВЕСТНО" был САМЫМ ВАЖНЫМ (в начале, с ⚠️)
   - txtPrb использовался для фильтрации вопросов
   - established_filters с confidence > 0.8 считались ИСТИННЫМИ

2. Добавить в промт:
   - Явную логику проверки冗антности (redundancy)
   - Проверку: "если txtPrb содержит X, НЕ спрашивай про X"
   - Примеры bad/good вопросов на основе txtPrb

3. Усилить запреты:
   - Двойные вопросы (через "или", "и")
   - Закрытые вопросы (кроме 90%+ кандидата)
   - Перечисления в скобках

4. Добавить позитивные примеры:
   - "✅ ХОРОШО: Опишите что именно сломалось"
   - "✅ ХОРОШО: Где именно это произошло?"
   - С объяснением КАК эти вопросы приближают к решению

### 6.2. Дать конкретный шаблон промта

**Структура:**
```
⚠️ КРИТИЧЕСКИ ВАЖНО: УЖЕ ИЗВЕСТНО
[txtPrb] + [established_filters с confidence > 0.8]

🎯 ЗАДАЧА (одной строкой, без лишней теории)

📋 КАНДИДАТЫ (сразу JSON, без "Текущая ситуация")

💬 ИСТОРИЯ (последние 2-3 сообщения)

❌ ЗАПРЕЩЕННЫЕ ПАТТЕРНЫ (с примерами)

✅ РАЗРЕШЕННЫЕ ПАТТЕРНЫ (с примерами)

Вопрос:
```

### 6.3. Показать реальный пример улучшенного промта

На диалоге выше показать:
1. Как бы выглядел УЛУЧШЕННЫЙ промт на шаге 8 (пользователь: "отопление")
2. Какой вопрос сгенерировал бы LLM с этим промтом
3. Почему этот вопрос ЛУЧШЕ текущего

---

## 7. ОГРАНИЧЕНИЯ И КОНТЕКСТ

### 7.1. Технические ограничения
- Модель: YandexGPT (Lite/Pro)
- Максимальная длина промта: ~4000 токенов
- Нельзя менять архитектуру микросервисов
- Можно менять ТОЛЬКО промт MainAgent

### 7.2. Бизнес-ограничения
- Бот должен звучать как человек (не робот)
- Нельзя использовать эмодзи
- Стиль: прямой, деловой, без избыточной вежливости
- Основной канал: ГОЛОСОВОЙ интерфейс (через оператора)
- Оператор не может нажимать кнопки - только свободный текст

### 7.3. Ограничения диалога
- Пользователь не технический (не знает терминов "Инцидент/Запрос")
- Пользователь может отвечать односложно ("да", "нет", "отопление")
- Пользователь может раздражаться ("я уже сказал")
- Нельзя перегружать вопрос (>10 слов)

---

## 8. ВЫХОДНОЙ ФОРМАТ

Твоя работа должна включать:

1. **Анализ текущего промта** (5-7 проблем с объяснением)
2. **Улучшенная архитектура промта** (структура с пояснением)
3. **Шаблон улучшенного промта** (с параметрами в скобках)
4. **Реальный пример** (заполненный шаблон на диалоге выше)
5. **Объяснение улучшений** (почему это сработает)
6. **План тестирования** (как проверить что улучшилось)

---

**Важно:** Ты не пишешь код - ты предлагаешь архитектуру промта. Код реализует разработчик, твоя задача - дать промт который будет работать.

Дай развернутый ответ с примерами и объяснениями.

---

## 9. ПОЛНАЯ СТРУКТУРА БАЗЫ ДАННЫХ

### 9.1. Основная таблица услуг: services_catalog

```sql
CREATE TABLE services_catalog (
    -- Первичный ключ
    service_id INTEGER PRIMARY KEY DEFAULT nextval('services_catalog_service_id_seq'::regclass),
    
    -- Основные поля
    scenario_id VARCHAR(20) NOT NULL UNIQUE,
    scenario_name VARCHAR(255) NOT NULL,
    description_for_search TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Внешние ключи на справочники (старая система)
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
    
    -- Метаданные
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Индексы для поиска
CREATE INDEX idx_services_catalog_active ON services_catalog(is_active);
CREATE INDEX idx_services_catalog_active_category ON services_catalog(category_id) WHERE is_active = TRUE;
CREATE INDEX idx_services_catalog_category_id ON services_catalog(category_id);
CREATE INDEX idx_services_catalog_description_trgm ON services_catalog USING gin(description_for_search gin_trgm_ops);
CREATE INDEX idx_services_catalog_scenario_name_trgm ON services_catalog USING gin(scenario_name gin_trgm_ops);
```

### 9.2. Справочники (ref_* таблицы)

```sql
-- Категории услуг
CREATE TABLE ref_categories (
    category_id SMALLINT PRIMARY KEY,
    category_code VARCHAR(50) NOT NULL UNIQUE,
    category_name VARCHAR(255) NOT NULL,
    description TEXT,
    icon_name VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Данные: 13 категорий
-- 40: Озеленение, 41: Ремонт МАФ и покрытий, 42: Санитария, 43: Электричество,
-- 44: Конструктив, 45: Отопление, 46: Водоснабжение, 47: Газоснабжение,
-- 48: Вентиляция, 49: Лифты, 50: Пожарная безопасность, 51: Канализация,
-- 52: Информационные запросы

-- Типы локаций
CREATE TABLE ref_localization (
    localization_id SMALLINT PRIMARY KEY,
    localization_code VARCHAR(50) NOT NULL UNIQUE,
    localization_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Типы услуг (Инцидент/Запрос)
CREATE TABLE ref_service_types (
    type_id SMALLINT PRIMARY KEY,
    type_code VARCHAR(50) NOT NULL UNIQUE,
    type_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Виды услуг
CREATE TABLE ref_service_kinds (
    kind_id SMALLINT PRIMARY KEY,
    type_id SMALLINT NOT NULL REFERENCES ref_service_types(type_id),
    kind_code VARCHAR(50) NOT NULL UNIQUE,
    kind_name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Объекты
CREATE TABLE ref_objects (
    object_id SMALLINT PRIMARY KEY,
    category_id SMALLINT REFERENCES ref_categories(category_id),
    object_code VARCHAR(50) NOT NULL UNIQUE,
    object_name VARCHAR(255) NOT NULL,
    description TEXT,
    is_common BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 9.3. Таблица логов диалогов

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
    processing_time_ms INTEGER,
    llm_provider VARCHAR(100),
    llm_model VARCHAR(100),
    tokens_used INTEGER,
    cost_rub NUMERIC(10,6),
    timestamp TIMESTAMPTZ DEFAULT now(),
    metadata JSONB
);

CREATE INDEX idx_dialog_logs_dialog_id ON dialog_logs(dialog_id);
CREATE INDEX idx_dialog_logs_user_id ON dialog_logs(user_id);
CREATE INDEX idx_dialog_logs_timestamp ON dialog_logs(timestamp);
```

### 9.4. Примеры данных из services_catalog

```sql
-- Топ-10 услуг
SELECT service_id, scenario_name, incident_type, category, location_type
FROM services_catalog
WHERE is_active = TRUE
ORDER BY service_id
LIMIT 10;

-- Результат:
-- service_id | scenario_name                            | incident_type | category      | location_type  
-- -----------+-------------------------------------------+---------------+---------------+---------------
-- 1          | Упало дерево/ветка на провода/дом/дорога  | Инцидент      | Озеленение   | Общедомовое
-- 2          | Уход за зелёными зонами...              | Инцидент      | Озеленение   | Общедомовое
-- 3          | Разрушение асфальта, ямы...             | Инцидент      | Ремонт МАФ... | Общедомовое
-- 4          | Сломанны малые архитектурные формы      | Инцидент      | Ремонт МАФ... | Общедомовое
-- 5          | Отмостка                                | Инцидент      | Ремонт МАФ... | Общедомовое
-- 6          | Очистка лотков и приямков водоотведения | Инцидент      | Санитария    | Общедомовое
-- 7          | Мусорные контейнеры переполнены         | Инцидент      | Санитария    | Общедомовое
-- 8          | Снег и наледь на территории            | Инцидент      | Санитария    | Общедомовое
-- 9          | Дезинсекция/дератизация                | Инцидент      | Санитария    | Общедомовое
-- 10         | Засор ливнёвой канализации              | Инцидент      | Санитария    | Общедомовое

-- Распределение по фильтрам
SELECT incident_type, category, location_type, COUNT(*) 
FROM services_catalog 
WHERE is_active = TRUE 
GROUP BY incident_type, category, location_type 
ORDER BY incident_type, category, location_type;

-- Результат (20 строк):
-- incident_type | category        | location_type  | count 
-- --------------+-----------------+----------------+-------
-- Запрос        | Водоснабжение   | Индивидуальное | 2
-- Запрос        | Газоснабжение   | Индивидуальное | 1
-- Запрос        | Информационные  | Индивидуальное | 12
-- Запрос        | Канализация     | Индивидуальное | 1
-- Запрос        | Отопление       | Индивидуальное | 1
-- Запрос        | Электричество   | Индивидуальное | 3
-- Инцидент      | Вентиляция      | Общедомовое    | 2
-- Инцидент      | Водоснабжение   | Индивидуальное | 2
-- Инцидент      | Водоснабжение   | Общедомовое    | 3
-- Инцидент      | Газоснабжение   | Индивидуальное | 1
-- Инцидент      | Канализация     | Индивидуальное | 1
-- Инцидент      | Канализация     | Общедомовое    | 2
-- Инцидент      | Конструктив     | Общедомовое    | 10
-- Инцидент      | Лифты           | Общедомовое    | 1
-- Инцидент      | Озеленение      | Общедомовое    | 2
-- Инцидент      | Отопление       | Общедомовое    | 4
-- Инцидент      | Пожарная безоп. | Общедомовое    | 4
-- Инцидент      | Ремонт МАФ      | Общедомовое    | 3
-- Инцидент      | Санитария       | Общедомовое    | 9
-- Инцидент      | Электричество   | Общедомовое    | 4
```

---

## 10. ЛИСТИНГИ ПИТОНСКОГО КОДА

### 10.1. MainAgent - главный координатор

**Файл:** `/var/www/komunal-dom_ru/main_agent.py` (2600+ строк)

#### 10.1.1. Инициализация

```python
class MainAgent:
    """
    Главный Агент координирует работу микросервисов:
    
    ВОРОНКА ТОЧНОСТИ:
    1. Сначала запускаем БЫСТРЫЕ микросервисы параллельно
    2. Анализируем результаты быстрых сервисов
    3. ЗАПУСКАЕМ AI ТОЛЬКО ПРИ НУЖДЕ
    """
    
    def __init__(self):
        self.tag_search = None
        self.semantic_search = None
        self.vector_search = None
        self.ai_agent = None
        self.filter_detection = None  # Сервис определения фильтров
        self.problem_accumulator = None  # Сервис накопления проблемы (txtPrb)
        self.confidence_threshold = 0.75
        
        # Кэш фильтров из БД (для промта)
        self._categories_cache = None
        self._objects_cache = None
        self._location_types_cache = None
        self._incident_types_cache = None
        
        self._init_services()
        self._load_filters_from_db()
```

#### 10.1.2. Основной метод обработки

```python
async def process_service_detection(
    self, 
    message_text: str, 
    user_context: Dict = None
) -> Dict:
    """
    Основной метод определения услуги через воронку точности
    
    Args:
        message_text: Текст сообщения пользователя
        user_context: Контекст (история диалога, txtPrb, etc.)
    
    Returns:
        Dict: {
            'status': 'SUCCESS' | 'AMBIGUOUS' | 'ERROR',
            'service_id': int | None,
            'service_name': str | None,
            'message': str,  # Вопрос пользователю
            'candidates': List[Dict],
            '_metadata': Dict  # Для отладки
        }
    """
    # Извлекаем параметры
    original_message = message_text
    is_followup = user_context.get('is_followup', False) if user_context else False
    dialog_history = user_context.get('dialog_history', []) if user_context else []
    
    # ===== ШАГ 1: ProblemAccumulationService - накопление txtPrb =====
    txtPrb = ""
    accumulated_fields = {}
    established_filters = {}
    
    if self.problem_accumulator and is_followup:
        accumulation_result = await self.problem_accumulator.extract_and_accumulate(
            message_text=message_text,
            current_problem=txtPrb,
            bot_question=last_bot_question,
            dialog_history=dialog_history
        )
        
        txtPrb = accumulation_result['updated_problem']
        accumulated_fields = accumulation_result['fields']
        established_filters = self.problem_accumulator.calculate_filter_confidence(
            txtPrb, accumulated_fields
        )
    
    # ===== ШАГ 2: Параллельный запуск микросервисов =====
    search_tasks = []
    if self.tag_search:
        search_tasks.append(self._run_tag_search(message_text))
    if self.semantic_search:
        search_tasks.append(self._run_semantic_search(message_text))
    if self.vector_search:
        search_tasks.append(self._run_vector_search(message_text))
    
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    
    # ===== ШАГ 3: AI Orchestrator - умное объединение =====
    orch_result = await self._orchestrate_microservices(
        message_text=search_text,
        search_results=search_results,
        dialog_history=dialog_history,
        txtPrb=txtPrb,
        established_filters=established_filters
    )
    
    if orch_result.get('status') == 'SUCCESS':
        return orch_result
    elif orch_result.get('status') == 'AMBIGUOUS':
        return orch_result
    
    # ===== ШАГ 4: FilterDetectionService - фильтрация по фильтрам =====
    if self.filter_detection:
        filter_result = await self.filter_detection.detect_filters(
            original_message, dialog_history
        )
        
        filters = filter_result.get('filters', {})
        # Фильтруем кандидатов по filters
        filtered_candidates = [...]
        
        if len(filtered_candidates) == 1:
            return {'status': 'SUCCESS', ...}
    
    # ===== ШАГ 5: Генерация уточняющего вопроса =====
    clarification_result = await self._generate_smart_clarification(
        candidates_with_attrs=filtered_candidates,
        original_message=original_message,
        is_followup=is_followup,
        dialog_history=dialog_history,
        txtPrb=txtPrb,
        established_filters=established_filters
    )
    
    return clarification_result
```

#### 10.1.3. Генерация вопросов через AI

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
            'question': str,  # Сгенерированный вопрос
            'prompt': str,    # Промт отправленный в LLM
            'response': str,  # Ответ от LLM
            'model': str,     # Модель использованная
            'usage': Dict     # Информация об использовании токенов
        }
    """
    # Формируем промт для AI
    prompt = self._build_question_prompt(
        context=context,
        dialog_history=dialog_history,
        candidates=candidates,
        established_filters=established_filters,
        txtPrb=txtPrb,
        question_type=question_type
    )
    
    # Вызываем AI через AIAgentService
    if self.ai_agent:
        # ГИБРИДНАЯ МОДЕЛЬ
        # Для вопросов к пользователю: Pro (качество критично!)
        # Для остальных задач: Lite
        question_types_requiring_pro = ['clarification', 'what_happened', 'location', 'details']
        model = 'pro' if question_type in question_types_requiring_pro else 'lite'
        
        response, usage = await self.ai_agent.call_llm(
            prompt=prompt,
            provider='yandexgpt',
            model=model
        )
        question = response.strip()
        
        # Post-processing проверки
        question = self._fix_double_questions(question)
        question = self._validate_question_not_redundant(
            question=question,
            txtPrb=txtPrb,
            established_filters=established_filters
        )
        
        return {
            'question': question,
            'prompt': prompt,
            'response': response,
            'model': usage.get('model', 'unknown'),
            'usage': usage
        }
```

#### 10.1.4. Пост-валидация вопросов

```python
def _validate_question_not_redundant(
    self, 
    question: str, 
    txtPrb: str = None, 
    established_filters: Dict = None
) -> str:
    """
    ПРОВЕРЯЕТ, что вопрос НЕ спрашивает то, что УЖЕ известно
    
    ⚠️ КРИТИЧЕСКИ ВАЖНО: Этот метод DETECTS но НЕ FIXES все проблемы!
    Нужна LLM-валидация вопроса ДО отправки пользователю
    """
    if not question:
        return question
    
    question_lower = question.lower()
    
    # ПРОВЕРКА 1: Если в txtPrb есть локация, а вопрос "где?"
    if txtPrb and any(loc in txtPrb.lower() for loc in ['зал', 'ванная', 'кухн', 'спальн']):
        if any(word in question_lower for word in ['где', 'какое место', 'в какой комнат']):
            logger.warning(f"⚠️ REDUNDANT вопрос (локация известна): {question}")
            return "Уточните, пожалуйста, детали проблемы."  # Fallback
    
    # ПРОВЕРКА 2: established_filters с high confidence
    if established_filters:
        location_filter = established_filters.get('location')
        if location_filter and location_filter.get('confidence', 0) > 0.8:
            if any(word in question_lower for word in ['где', 'место', 'локаци']):
                logger.warning(f"⚠️ REDUNDANT вопрос (location фильтр): {question}")
                return "Уточните детали."
    
    return question
```

**ПРОБЛЕМА:** Этот метод проверяет только KEYWORDS, не семантику!

### 10.2. ProblemAccumulationService - накопление txtPrb

**Файл:** `/var/www/komunal-dom_ru/problem_accumulation_service.py` (400+ строк)

```python
class ProblemAccumulationService:
    """
    Микросервис для итеративного накопления описания проблемы.
    
    Принцип работы:
    - 'привет' → txtPrb = '' (нет значимой информации)
    - 'у меня течет' → txtPrb = 'у пользователя течет'
    - 'Где течет?' - 'В зале' → txtPrb = 'у пользователя течет в зале'
    - 'Что именно течет' - 'Батарея' → txtPrb = 'у пользователя течет из батареи'
    """
    
    def __init__(self, ai_agent_service):
        self.ai_agent = ai_agent_service
    
    async def extract_and_accumulate(
        self,
        message_text: str,
        current_problem: str,
        bot_question: str = None,
        dialog_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Извлекает информацию из сообщения и накапливает описание проблемы
        
        Returns:
            {
                'updated_problem': str,  # Обновленное txtPrb
                'extracted_info': dict,
                'is_meaningful': bool,   # Содержит ли полезную информацию
                'new_info': str,
                'fields': {
                    'problem': str | None,
                    'location': str | None,
                    'source': str | None,
                    'category': str | None,
                    'severity': str | None,
                    'intensity': str | None,
                    'object': str | None
                }
            }
        """
        # Формируем промт для LLM
        prompt = self._create_accumulation_prompt(
            message_text, current_problem, bot_question, dialog_history
        )
        
        # Вызываем LLM
        response_text, usage = await self.ai_agent._call_yandex_gpt(prompt)
        
        # Парсим JSON
        result = self._parse_llm_response(response_text, current_problem)
        
        return result
```

**ПРОБЛЕМА:** txtPrb накапливается корректно, но MainAgent НЕ ИСПОЛЬЗУЕТ его для фильтрации вопросов!

### 10.3. FilterDetectionService - определение фильтров

**Файл:** `/var/www/komunal-dom_ru/filter_detection_service.py` (500+ строк)

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
    
    def _create_filter_detection_prompt(
        self, 
        message_text: str, 
        dialog_history: List[Dict]
    ) -> str:
        """
        Создание промпта для определения фильтров
        
        ИСПРАВЛЕНО: Загружает категории из БД вместо хардкода
        """
        # Формируем список категорий из БД
        categories_str = ", ".join([f'"{cat}"' for cat in self.categories_list])
        
        prompt = f"""Ты - опытный диспетчер управляющей компании. Проанализируй обращение и определи фильтры для поиска услуги.
        
История диалога:
{history_text}

Текущее сообщение: "{message_text}"

ДОСТУПНЫЕ КАТЕГОРИИ УСЛУГ:
{categories_str}

ПРИМЕРЫ ОБЪЕКТОВ ПО КАТЕГОРИЯМ:
{objects_examples_text}

Определи и верни JSON в формате:
{{
    "incident_type": "Инцидент" или "Запрос",
    "location_type": "Индивидуальное" или "Общедомовое",
    "category": одна из доступных категорий выше,
    "object_description": "МАКСИМУМ 3 СЛОВА",
    "confidence": 0.0-1.0,
    "reason": "обоснование выбора"
}}

⚠️⚠️⚠️ КРИТИЧЕСКИ ВАЖНО:
1. ТЕЧЕТ ВОДЫ = "Инцидент" (аварийная ситуация!)
2. ПРОРЫВ ТРУБЫ = "Инцидент" (авария!)
3. ЗАТОПЛЕНИЕ = "Инцидент" (угроза имуществу!)

Верни только JSON, без другого текста.
"""
        return prompt
```

---

## 11. ИЗМЕНЕНИЯ В КОДЕ (НЕ ТОЛЬКО ПРОМПТ!)

### 11.1. Что нужно изменить в коде

**КРИТИЧЕСКИ ВАЖНО:** Архитектор должен предложить не только УЛУЧШЕННЫЙ ПРОМПТ, но и ИЗМЕНЕНИЯ В КОДЕ!

#### 11.1.1. LLM-валидация сгенерированного вопроса

**ПРОБЛЕМА:** Текущий `_validate_question_not_redundant()` проверяет только keywords.

**РЕШЕНИЕ:** Добавить LLM-валидацию:

```python
async def _llm_validate_question_redundancy(
    self,
    question: str,
    txtPrb: str,
    established_filters: Dict
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
    prompt = f"""Ты - валидатор вопросов для AI-диспетчера.

ВОПРОС БОТА: "{question}"

УЖЕ ИЗВЕСТНАЯ ИНФОРМАЦИЯ:
txtPrb: "{txtPrb}"
Фильтры: {established_filters}

ЗАДАЧА: Определи, спрашивает ли вопрос то, что УЖЕ известно?

Верни JSON:
{{
    "is_redundant": true или false,
    "reason": "объяснение",
    "suggested_fix": "лучший вопрос или null"
}}

ПРИМЕРЫ:
- Вопрос: "Где именно?" при txtPrb="в зале" → is_redundant=true
- Вопрос: "Что именно?" при txtPrb="течет" → is_redundant=true
- Вопрос: "Какая локация?" при location=95% → is_redundant=true
"""
    
    response, usage = await self.ai_agent.call_llm(prompt, model='lite')
    result = json.loads(response)
    
    if result['is_redundant']:
        logger.warning(f"⚠️ LLM-detected REDUNDANT: {question}")
        return result
    
    return result
```

#### 11.1.2. Обработка "я уже сказал"

**ПРОБЛЕМА:** Бот не реагирует на раздражение пользователя.

**РЕШЕНИЕ:** Добавить детектор:

```python
def _detect_user_frustration(
    self,
    message_text: str,
    dialog_history: List[Dict]
) -> bool:
    """
    Детектирует раздражение пользователя
    
    Returns:
        bool: True если пользователь раздражен
    """
    frustration_keywords = [
        'я уже сказал', 'уже отвечал', 'повторяюсь',
        'не понимаю', 'какой еще раз', 'зачем спрашиваешь'
    ]
    
    if any(kw in message_text.lower() for kw in frustration_keywords):
        return True
    
    # Проверяем: 3+ одинаковых ответа подряд
    recent_user_responses = [
        msg.get('text', '').strip().lower()
        for msg in dialog_history[-6:]
        if msg.get('role') == 'user'
    ]
    
    if len(recent_user_responses) >= 3:
        if len(set(recent_user_responses[-3:])) == 1:
            return True
    
    return False
```

#### 11.1.3. Учет txtPrb при генерации вопроса

**ПРОБЛЕМА:** txtPrb не используется для фильтрации.

**РЕШЕНИЕ:** Добавить pre-check:

```python
async def _precheck_known_info(
    self,
    txtPrb: str,
    established_filters: Dict
) -> Dict:
    """
    Pre-check: что УЖЕ известно из txtPrb и фильтров
    
    Returns:
        Dict: {
            'known_location': str | None,
            'known_object': str | None,
            'known_problem': str | None,
            'known_category': str | None,
            'should_ask_location': bool,
            'should_ask_object': bool,
            'should_ask_problem': bool
        }
    """
    # Анализируем txtPrb через LLM
    prompt = f"""Извлеки известную информацию из описания проблемы:

"{txtPrb}"

Верни JSON:
{{
    "location": "зал" или null,
    "object": "труба" или null,
    "problem": "течет" или null,
    "category": "отопление" или null
}}
"""
    
    response, usage = await self.ai_agent.call_llm(prompt, model='lite')
    known_info = json.loads(response)
    
    return {
        'known_location': known_info.get('location'),
        'known_object': known_info.get('object'),
        'known_problem': known_info.get('problem'),
        'known_category': known_info.get('category'),
        'should_ask_location': known_info.get('location') is None,
        'should_ask_object': known_info.get('object') is None,
        'should_ask_problem': known_info.get('problem') is None
    }
```

### 11.2. Обновленный алгоритм MainAgent

```python
async def process_service_detection(...):
    # ... (существующий код)
    
    # ===== НОВЫЙ ШАГ: Pre-check известной информации =====
    if is_followup and txtPrb:
        precheck = await self._precheck_known_info(txtPrb, established_filters)
        
        # Если ВСЕ известное - можно определить услугу!
        if not any([
            precheck['should_ask_location'],
            precheck['should_ask_object'],
            precheck['should_ask_problem']
        ]):
            # Все известное - ищем услугу по фильтрам
            service = await self._find_service_by_filters(
                location=precheck['known_location'],
                object=precheck['known_object'],
                problem=precheck['known_problem'],
                category=precheck['known_category']
            )
            
            if service:
                return {
                    'status': 'SUCCESS',
                    'service_id': service['service_id'],
                    'service_name': service['scenario_name'],
                    'message': f"Понял, у вас: {service['scenario_name']}. Правильно?"
                }
    
    # ... (существующий код)
    
    # ===== НОВЫЙ ШАГ: LLM-валидация вопроса =====
    ai_result = await self._generate_ai_question(...)
    question = ai_result['question']
    
    # LLM-валидация на冗антность
    validation = await self._llm_validate_question_redundancy(
        question=question,
        txtPrb=txtPrb,
        established_filters=established_filters
    )
    
    if validation['is_redundant']:
        # Заменяем на suggested_fix или fallback
        question = validation['suggested_fix'] or "Уточните детали."
    
    return {'question': question, ...}
```

---

## 12. ОТЛАДКА ПО ШАБЛОНУ

### 12.1. Что такое "отладка по шаблону"?

**Отладка по шаблону** - это методика диагностики проблем в диалоговой системе, при которой для каждого этапа обработки сообщения создается детальный отчет по фиксированному шаблону.

**Принцип работы:**
1. После каждого сообщения пользователя сохраняется полный отчет в `/tmp/`
2. Отчет создается по фиксированному шаблону (см. ниже)
3. Отчет содержит ВСЮ информацию: входные параметры, txtPrb, фильтры, кандидатов, промты LLM, ответы
4. Архитектор может проанализировать отчет и найти проблему

### 12.2. Шаблон отчета

**Файл:** `/var/www/komunal-dom_ru/trace_report_service.py`

**Шаблон:**

```markdown
================================================================================
ОТЧЕТ ТРАССИРОВКИ ДИАЛОГА (улучшенный шаблон v2.0 - 2025-12-28)
================================================================================
Session ID: telegram_1049252307_20251228_133000
Канал: telegram
Всего сообщений: 6
Период: 2025-12-28 13:30:00 - 2025-12-28 13:31:45

================================================================================
ИСТОРИЯ txtPrb (накопление описания проблемы)
================================================================================

#1: (нет значимой информации)
#2: у пользователя течет
#3: у пользователя течет в зале
#4: у пользователя течет труба в зале
#5: у пользователя течет труба в зале (значимая информация)
#6: у пользователя течет труба в зале (значимая информация)

================================================================================
ДЕТАЛЬНАЯ ТРАССИРОВКА ПО СООБЩЕНИЯМ
================================================================================

СООБЩЕНИЕ #1
ID: 1261
Направление: inbound (пользователь → бот)
Текст: "привет"
Время: 2025-12-28 13:30:15

┌─── АНАЛИЗ СООБЩЕНИЯ ───┐
│                        │
├─ ЗНАЧИМАЯ ИНФОРМАЦИЯ:
❌ Нет (приветствие)
│
└─ ЗАКЛЮЧЕНИЕ:
⚠️ Приветствие - не содержит информации о проблеме

ОТВЕТ БОТА:
"Здравствуйте! Опишите вашу проблему, и я попробую помочь."

СООБЩЕНИЕ #2
ID: 1262
Направление: inbound
Текст: "у меня течет"
Время: 2025-12-28 13:30:25

┌─── АНАЛИЗ СООБЩЕНИЯ ───┐
│                        │
├─ ЗНАЧИМАЯ ИНФОРМАЦИЯ:
✅ Проблема: "течет"
│
└─ ЗАКЛЮЧЕНИЕ:
✅ Сообщение содержит ЗНАЧИМУЮ информацию

txtPrb после обработки: "у пользователя течет"

┌─── РЕЗУЛЬТАТЫ МИКРОСЕРВИСОВ ───┐
│                                │
├─ TagSearchService:
│  (нет кандидатов)
│
├─ VectorSearchService:
│  ID:7 | Устранение течи | 75.00%
│
├─ SemanticSearchService:
│  (нет кандидатов)
│
└─ AIAgentService:
   (не вызван)

─── ПЕРЕСЕЧЕНИЕ ───
Общий кандидат: 1
ID:7 | Устранение течи | 75.00%

┌─── ФИЛЬТРЫ (FilterDetectionService) ───┐
│                                         │
├─ ЗАПРОС К LLM:
"Извлеки фильтры из сообщения: 'у меня течет'"
│
├─ ОТВЕТ LLM:
{
  "incident": "Инцидент"
}
│
└─ ФАКТИЧЕСКИЕ ФИЛЬТРЫ:
incident = Инцидент (confidence: 85%)

METADATA:
service_detection:
  status: AMBIGUOUS
  message: "Опишите подробнее, что течёт и где это произошло?"
  candidates:
    - ID:7
      service_name: "Устранение течи"
      confidence: 75.00%
      source: "vector_search"
  accumulated_fields:
    problem: "течет"
  established_filters:
    incident:
      value: "Инцидент"
      confidence: 0.85

ОТВЕТ БОТА:
"Опишите подробнее, что течёт и где это произошло?"

...
```

### 12.3. Как использовать отчеты для отладки

**Пример анализа:**

**ШАГ 1:** Сгенерировать отчет для проблемного диалога

```python
from trace_report_service import generate_dialog_trace

path = await generate_dialog_trace('telegram_1049252307')
# Создаст: /tmp/_tras_diag_20251228_133000.md
```

**ШАГ 2:** Проанализировать отчет

**Проблема:** На шаге #7 бот спрашивает "Где именно?" при txtPrb="течет из трубы отопления в зале"

**Анализ отчета:**
```
СООБЩЕНИЕ #7
txtPrb: "у пользователя течет из трубы отопления в зале"

🔧 УСТАНОВЛЕННЫЕ ФИЛЬТРЫ:
- location: Индивидуальное (95%)
- category: Отопление (95%)
- incident: Инцидент (90%)

📋 СПИСОК КАНДИДАТОВ:
- ID:33 | Течь из трубы отопления в квартире | 98% (Отопление, Индивидуальное)

ОТВЕТ БОТА:
"Течёт из трубы в вашей квартире или в общедомовой системе?"
```

**ВЫВОД:** Бот игнорирует:
1. txtPrb содержит "зале" → Индивидуальное
2. location фильтр = Индивидуальное (95%)
3. Есть кандидат ID:33 с 98% confidence!

**ШАГ 3:** Исправление

Добавить в промт:
```
⚠️ КРИТИЧЕСКИ ВАЖНО: НЕ спрашивай локацию если:
- txtPrb содержит "зал/ванная/кухня/спальня" → location=Индивидуальное
- established_filters['location'] > 0.8 → localization известна
```

### 12.4. Команды для генерации отчетов

```bash
# По session_id
python trace_report_service.py --session-id telegram_1049252307_20251228_133000

# По telegram_user_id
python trace_report_service.py --telegram-user-id 1049252307

# Вывод в JSON
python trace_report_service.py --session-id web_123 --output json

# Просмотр последнего отчета
cat /tmp/_tras_diag_$(ls -t /tmp/_tras_diag_*.md | head -1 | xargs basename)

# Все отчеты
ls -lh /tmp/_tras_diag_*.md
```

### 12.5. Как это помогает архитектору

1. **Визуализация проблемы:** Видно где именно сломалась логика
2. **Полный контекст:** Все входные параметры, промты, ответы в одном месте
3. **История txtPrb:** Видно как накапливалась информация
4. **Результаты микросервисов:** Видно что нашли TagSearch, VectorSearch, AI
5. **Фильтры:** Видно какие фильтры установились и с какой уверенностью
6. **Кандидаты:** Полный список с % confidence
7. **Промты LLM:** Точные промты которые отправлялись в YandexGPT
8. **Ответы LLM:** Что вернула модель

**ПРИМЕР ИСПОЛЬЗОВАНИЯ:**

Архитектор получает отчет и видит:
```
СООБЩЕНИЕ #7
txtPrb: "у пользователя течет из трубы отопления в зале"
established_filters: location=95%, category=95%
candidates: ID:33 | Течь из трубы отопления | 98%

ОТВЕТ БОТА: "Течёт из трубы в вашей квартире или в общедомовой системе?"
```

Архитектор понимает:
- Проблема: Бот игнорирует location=95% и спрашивает локацию
- Решение: Добавить в промт: "ЕСЛИ location confidence > 0.8, НЕ спрашивать локацию!"
- Testing: Сгенерировать новый отчет после исправления и проверить

---

## 13. ВЫХОДНОЙ ФОРМАТ (ОБНОВЛЕННЫЙ)

Твоя работа должна включать:

### 13.1. Анализ текущего подхода
1. **5-7 проблем в промте** (с объяснением и примерами из диалога)
2. **3-5 проблем в коде** (что нужно изменить кроме промта)
3. **Архитектурные проблемы** (почему текущая система не работает)

### 13.2. Улучшенная архитектура
1. **Новая структура промта** (пояснить почему лучше)
2. **Изменения в коде** (конкретные методы, что добавить)
3. **LLM-валидация вопроса** (код + промт)
4. **Обработка "я уже сказал"** (детектор + стратегия)
5. **Pre-check известной информации** (как использовать txtPrb)

### 13.3. Шаблон улучшенного промта
1. **Полный шаблон** с параметрами `[PARAMETER]`
2. **Объяснение каждого блока**
3. **Почему эта структура работает**

### 13.4. Реальный пример
1. **Заполненный шаблон** на шаге #8 диалога ("отопление")
2. **Сгенерированный вопрос** (какой должен быть)
3. **Почему этот вопрос лучше** текущего

### 13.5. План внедрения
1. **Изменения в коде** (псевдокод + файлы)
2. **Изменения в промте** (diff: до/после)
3. **Тестирование** (как проверить что работает)
4. **Отладка по шаблону** (как использовать trace_report_service)

### 13.6. Критерии успеха
1. **Метрики:**
   - % диалогов с "я уже сказал" < 5%
   - Среднее количество сообщений до SUCCESS < 5
   - %冗антных вопросов < 1%
2. **Качественные:**
   - Бот не спрашивает то, что уже в txtPrb
   - Бот не задает двойные вопросы
   - Бот реагирует на раздражение пользователя

---

**Важно:** Ты не пишешь код - ты предлагаешь архитектуру (промт + изменения в коде). Код реализует разработчик, твоя задача - дать решение которое будет работать.

Дай развернутый ответ с примерами, кодом (псевдокод) и объяснениями.
