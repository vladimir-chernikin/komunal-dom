# FILES_TO_READ_FIRST - Коммунальный Дом

**Дата:** 2026-03-19
**Для:** Внешнего ревьюера

---

## 1. ПОРЯДОК ЧТЕНИЯ (PRIORITIZED)

### Шаг 1: Понять проект (30 минут)

| Файл | Строк | Почему важен | Что смотреть |
|---|---|---|---|
| **komunal_dom/settings.py** | 222 | Главный конфигурационный файл | INSTALLED_APPS, MIDDLEWARE, DATABASES, TEMPLATES |
| **komunal_dom/urls.py** | 37 | Главный URL routing | Какие URL, какие apps |
| **.env** (не коммитить!) | - | Секреты (DB, API) | Какие внешние сервисы |

### Шаг 2: Основная логика (1-2 часа)

| Файл | Строк | Почему важен | Что смотреть |
|---|---|---|---|
| **main_agent.py** | ~500 | Главный координатор AI | Как координирует микросервисы |
| **message_handler_service.py** | ~400 | Обработка сообщений | Единая точка входа |
| **portal/views.py** | ~1000 | Основные views (39KB!) | Нужен рефакторинг |
| **portal/models.py** | 219 | Основные модели | AIPrompt, UserProfile, ServicesCatalog |
| **message_handler/models.py** | 458 | Логирование сообщений | MessageLog, CommunicativeScript |

### Шаг 3: AI и поиск (1-2 часа)

| Файл | Строк | Почему важен | Что смотреть |
|---|---|---|---|
| **ai_agent_service.py** | ~300 | AI агент (YandexGPT) | Все вызовы LLM через этот сервис |
| **vector_search_service.py** | ~400 | Векторный поиск | Embedding, косинусное сходство |
| **tag_search_service.py** | ~300 | Поиск по тегам | pg_trgm, pymorphy2, rapidfuzz |
| **filter_detection_service.py** | ~300 | Детекция фильтров | location, category, incident |
| **problem_accumulation_service.py** | ~200 | Накопление txtPrb | Итеративное накопление информации |

### Шаг 4: Runtime (30 минут)

| Файл | Строк | Почему важен | Что смотреть |
|---|---|---|---|
| **gunicorn-komunal-dom.service** | - | Systemd сервис (gunicorn) | Конфигурация workers |
| **enhanced-aspect-bot.service** | - | Systemd сервис (бот) | Telegram бот |
| **nginx conf** | - | Nginx конфигурация | Прокси на gunicorn |

---

## 2. ТОП-15 ФАЙЛОВ ДЛЯ КОД-РЕВЬЮ

Если ограничены во времени, смотреть в этом порядке:

### Критичные (Priority 1 - 2-3 часа):

1. **main_agent.py** - Главный координатор AI
2. **message_handler_service.py** - Обработка сообщений
3. **portal/views.py** - Основные views (39KB, нужен рефакторинг)
4. **ai_agent_service.py** - AI агент
5. **vector_search_service.py** - Векторный поиск

### Важные (Priority 2 - 1-2 часа):

6. **filter_detection_service.py** - Детекция фильтров
7. **message_handler/models.py** - Логирование (458 строк)
8. **portal/models.py** - Основные модели
9. **tag_search_service.py** - Поиск по тегам
10. **komunal_dom/settings.py** - Настройки

### Полезные (Priority 3 - 1 час):

11. **problem_accumulation_service.py** - Накопление txtPrb
12. **portal/admin.py** - Админка УК
13. **komunal_dom/urls.py** - URL routing
14. **komunal_dom/middleware.py** - SubdomainMiddleware
15. **portal/urls.py** - Portal URL routing

---

## 3. ПОДРОБНОЕ ОПИСАНИЕ КРИТИЧНЫХ ФАЙЛОВ

### main_agent.py

**Расположение:** `/var/www/komunal-dom_ru/main_agent.py`

**Назначение:** Главный координатор AI-системы

**Ключевые методы:**
- `determine_service()` - определение услуги (воронка точности)
- `check_success_conditions()` - проверка условий для создания заявки
- `generate_response()` - генерация ответа пользователю
- `create_request()` - создание заявки

**Что искать при ревью:**
- ✅ Правильно ли координирует микросервисы?
- ✅ Есть ли обработка ошибок?
- ✅ Нет ли hardcoded значений?
- ⚠️ Нужен ли рефакторинг?

**Связи:**
- Вызывает: VectorSearchService, TagSearchService, SemanticSearchService, AIAgentService
- Используется: MessageHandlerService

---

### message_handler_service.py

**Расположение:** `/var/www/komunal-dom_ru/message_handler_service.py`

**Назначение:** Единая точка входа для обработки сообщений из всех каналов

**Ключевые методы:**
- `handle_incoming_message()` - обработка входящего сообщения
- `send_message()` - отправка ответа

**Что искать при ревью:**
- ✅ Правильно ли определяется канал?
- ✅ Есть ли логирование?
- ✅ Правильно ли обрабатываются ошибки?
- ⚠️ Нужен ли рефакторинг?

**Связи:**
- Вызывает: MainAgent, DialogLoggerService
- Используется: enhanced_aspect_bot.py, portal/views.py

---

### portal/views.py

**Расположение:** `/var/www/komunal-dom_ru/portal/views.py`

**Назначение:** Основные views (39KB - нужен рефакторинг!)

**Что искать при ревью:**
- ⚠️ God Object - нужен рефакторинг
- ⚠️ Слишком много обязанностей
- ⚠️ Сложно понимать и тестировать

**Рекомендации:**
- Разбить на компоненты (views/*.py):
  - `views/requests.py` - заявки
  - `views/admin.py` - админка УК
  - `views/residents.py` - жители
  - `views/services.py` - услуги

---

### ai_agent_service.py

**Расположение:** `/var/www/komunal-dom_ru/ai_agent_service.py`

**Назначение:** AI агент (YandexGPT)

**Ключевые методы:**
- `generate_response()` - генерация ответа
- `classify_message()` - классификация сообщения

**Что искать при ревью:**
- ✅ Все ли вызовы LLM идут через этот сервис?
- ✅ Есть ли обработка ошибок?
- ✅ Есть ли логирование (tokеns, стоимость)?
- ⚠️ Нужен ли retry механизм?

**КРИТИЧНО:** Все вызовы LLM ТОЛЬКО через AIAgentService!

---

### vector_search_service.py

**Расположение:** `/var/www/komunal-dom_ru/vector_search_service.py`

**Назначение:** Векторный поиск (Yandex Embeddings API)

**Ключевые методы:**
- `search_by_embedding()` - поиск по embedding
- `cosine_similarity()` - косинусное сходство

**Что искать при ревью:**
- ✅ Правильно ли вычисляется косинусное сходство?
- ✅ Правильно ли сливаются результаты (0.6 * tag + 0.4 * service)?
- ✅ Есть ли кеширование?
- ⚠️ Нужен ли fallback если API недоступен?

---

### filter_detection_service.py

**Расположение:** `/var/www/komunal-dom_ru/filter_detection_service.py`

**Назначение:** Детекция фильтров (location, category, incident)

**Ключевые методы:**
- `detect_location_type()` - Индивидуальное / Общедомовое
- `detect_category()` - Категория услуги
- `detect_incident_type()` - Инцидент / Запрос

**Что искать при ревью:**
- ✅ Правильно ли определяются фильтры?
- ✅ Есть ли обработка ошибок?
- ✅ Есть ли логирование?
- ⚠️ Нужен ли рефакторинг?

---

### message_handler/models.py

**Расположение:** `/var/www/komunal-dom_ru/message_handler/models.py`

**Назначение:** Модели для логирования сообщений

**Ключевые модели:**
- `MessageLog` - Лог всех сообщений
- `CommunicativeScript` - Скрипты бота
- `APIErrorLog` - Лог ошибок API

**Что искать при ревью:**
- ✅ Правильно ли определены поля?
- ✅ Есть ли индексы?
- ✅ Есть ли внешние ключи?
- ⚠️ Нужны ли дополнительные связи?

---

### portal/models.py

**Расположение:** `/var/www/komunal-dom_ru/portal/models.py`

**Назначение:** Основные модели

**Ключевые модели:**
- `AIPrompt` - AI промпты бота
- `UserProfile` - Профили пользователей
- `SemanticPattern` - Семантические паттерны
- `ServicesCatalog` - Каталог услуг (unmanaged)

**Что искать при ревью:**
- ⚠️ AIPrompt - дублирует PromptTemplate?
- ⚠️ SemanticPattern - вытеснен CommunicativeScript?
- ⚠️ ServicesCatalog - почему unmanaged?
- ✅ UserProfile - правильные ли роли?

---

## 4. ФАЙЛЫ ДЛЯ ДИАГНОСТИКИ ПРОБЛЕМ

### Если проблемы с AI:

1. **main_agent.py** - Главный координатор
2. **ai_agent_service.py** - AI агент
3. **vector_search_service.py** - Векторный поиск
4. **filter_detection_service.py** - Детекция фильтров

### Если проблемы с логированием:

1. **message_handler/models.py** - MessageLog
2. **dialog_logger_service.py** - Логирование
3. **trace_report_service.py** - Отчеты

### Если проблемы с производительностью:

1. **performance_tracer.py** - Трассировка
2. **performance_report_service.py** - Отчеты
3. **dialog_trace_service.py** - Трассировка диалогов

### Если проблемы с деплоем:

1. **komunal_dom/settings.py** - Настройки
2. **gunicorn-komunal-dom.service** - Systemd
3. **nginx conf** - Nginx конфигурация

---

## 5. ФАЙЛЫ ДЛЯ УЛУЧШЕНИЯ

### Для рефакторинга (приоритет 1):

1. **portal/views.py** - Разбить на компоненты
2. **main_agent.py** - Выделить интерфейсы
3. **ai_agent_service.py** - Добавить адаптеры

### Для очистки (приоритет 2):

1. **old/** - Удалить 50+ файлов
2. **doc/ и docs/** - Объединить
3. **backups_20260223/*** - Архивировать

### Для унификации (приоритет 3):

1. **AIPrompt** (portal) vs **PromptTemplate** (llm_tester) - Объединить
2. **SemanticPattern** (portal) vs **CommunicativeScript** (message_handler) - Разделить

---

## 6. ЧТО НЕ СМОТРЕТЬ ПЕРВЫМ

### Не критично (можно пропустить):

1. **test_bot_simulator.py** - Только для тестирования
2. **create_filter_prompts.py** - Временный скрипт
3. **analysis_*.md** - Анализ (старые файлы)
4. **old/** - Рудименты

### Экспериментальное (можно пропустить):

1. **gigachat_service.py** - Неизвестно, используется ли
2. **message_cleaner_service.py** - Неизвестно, используется ли
3. **performance_tracer.py** - Для диагностики

---

## 7. ЧЕК-ЛИСТ РЕВЬЮ

### Шаг 1: Понять архитектуру (30 мин)

- [ ] Прочитать settings.py
- [ ] Прочитать urls.py
- [ ] Понять структуру apps
- [ ] Понять URL routing

### Шаг 2: Изучить основную логику (2-3 часа)

- [ ] Прочитать main_agent.py
- [ ] Прочитать message_handler_service.py
- [ ] Прочитать portal/views.py (критично!)
- [ ] Прочитать portal/models.py
- [ ] Прочитать message_handler/models.py

### Шаг 3: Изучить AI и поиск (2-3 часа)

- [ ] Прочитать ai_agent_service.py
- [ ] Прочитать vector_search_service.py
- [ ] Прочитать tag_search_service.py
- [ ] Прочитать filter_detection_service.py
- [ ] Прочитать problem_accumulation_service.py

### Шаг 4: Проверить runtime (30 мин)

- [ ] Проверить gunicorn service
- [ ] Проверить nginx conf
- [ ] Проверить .env (не коммитить!)

### Шаг 5: Выписать проблемы (1 час)

- [ ] Выписать критические проблемы
- [ ] Выписать рудименты
- [ ] Выписать рекомендации

---

**ВЫВОД:** Для эффективного ревью начинать с understanding (settings.py, urls.py), затем основная логика (main_agent.py, message_handler_service.py, portal/views.py), затем AI и поиск (ai_agent_service.py, vector_search_service.py, filter_detection_service.py). Всего 5-7 часов на полное ревью. Критичные файлы: main_agent.py, message_handler_service.py, portal/views.py (нужен рефакторинг).
