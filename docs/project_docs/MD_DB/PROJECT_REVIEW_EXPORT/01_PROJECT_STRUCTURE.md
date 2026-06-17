# PROJECT STRUCTURE - Коммунальный Дом

**Дата:** 2026-03-19
**Корневая директория:** /var/www/komunal-dom_ru

---

## 1. ДЕРЕВО ВЕРХНЕГО УРОВНЯ

```
/var/www/komunal-dom_ru/
├── komunal_dom/              # Главный Django проект (settings, urls, wsgi)
├── portal/                   # Основное приложение (заявки, услуги, админка УК)
├── nsi/                      # НСИ - справочники (Company, EquipmentType)
├── message_handler/          # Логирование сообщений (MessageLog, CommunicativeScript)
├── llm_tester/               # LLM Tester (тестирование промптов)
├── database_viewer/          # СУБД SQL интерфейс
├── file_manager/             # Файловый менеджер
├── kladr/                    # База КЛАДР (адреса)
│
├── AI-сервисы (в корне - 20+ файлов):
│   ├── main_agent.py                     # Главный координатор AI
│   ├── message_handler_service.py        # Обработка сообщений
│   ├── ai_agent_service.py               # AI агент (YandexGPT)
│   ├── vector_search_service.py          # Векторный поиск
│   ├── tag_search_service.py             # Поиск по тегам
│   ├── semantic_search_service.py        # Семантический поиск
│   ├── filter_detection_service.py       # Детекция фильтров
│   ├── problem_accumulation_service.py   # Накопление txtPrb
│   ├── dialog_logger_service.py          # Логирование диалогов
│   ├── dialog_trace_service.py           # Трассировка диалогов
│   ├── trace_report_service.py           # Отчеты трассировки
│   ├── performance_report_service.py     # Отчеты о производительности
│   ├── performance_tracer.py             # Трассировка производительности
│   ├── address_extractor_service.py      # Извлечение адресов
│   ├── message_cleaner_service.py        # Очистка сообщений
│   ├── communicative_scripts_service.py   # Коммуникативные скрипты
│   ├── gigachat_service.py               # GigaChat сервис
│   ├── enhanced_aspect_bot.py            # Telegram бот
│   └── test_bot_simulator.py             # Симулятор бота
│
├── settings/конфигурация:
│   ├── komunal_dom/settings.py    # Основной settings
│   ├── komunal_dom/urls.py         # Главный URL routing
│   ├── komunal_dom/wsgi.py         # WSGI приложение
│   ├── manage.py                   # Django manage.py
│   └── .env                        # Секреты (DB, API ключи)
│
├── runtime:
│   ├── static/                     # Статические файлы (исходники)
│   ├── staticfiles/                # Собранная статика (collectstatic)
│   ├── media/                      # Загруженные файлы
│   ├── templates/                  # Глобальные шаблоны
│   ├── logs/                       # Логи приложения
│   └── venv/                       # Виртуальное окружение
│
├── рудименты (нужна очистка):
│   ├── old/                        # 50+ старых файлов (РУДИМЕНТ!)
│   ├── doc/                        # Документация (дубликат docs/?)
│   ├── docs/                       # Документация (дубликат doc/?)
│   ├── backups/                    # Backup'ы БД
│   ├── backups_20260223/           # Старые backup'ы (РУДИМЕНТ?)
│   ├── backups_20260223_133420/    # Старые backup'ы (РУДИМЕНТ?)
│   ├── migrations/                 # Миграции (why not in apps?)
│   ├── migrations_fixes/           # Временные fix'ы (РУДИМЕНТ?)
│   ├── prompts_backup/             # Бэкапы промптов (нужны?)
│   ├── scripts/                    # Скрипты (какие?)
│   └── instructions/               # Инструкции (какие?)
│
└── testing:
    ├── tests/                      # Тесты
    └── tmp_archive/                # Временные архивы
```

---

## 2. DJANGO APPS

### Официальные apps (из settings.py):

| App | Назначение | Models | Views | URLs |
|---|---|---|---|---|
| **komunal_dom** | Главный проект | - | custom_logout | / |
| **portal** | Основное приложение | AIPrompt, UserProfile, SemanticPattern, ServicesCatalog | ✓ | ✓ |
| **nsi** | Справочники | Company, EquipmentType | - | - |
| **message_handler** | Логирование сообщений | MessageLog, CommunicativeScript, APIErrorLog | ✓ | /chat/ |
| **llm_tester** | Тестирование промптов | PromptTemplate, LLMRequestLog | ✓ | /llm-tester/ |
| **database_viewer** | СУБД SQL интерфейс | SavedQuery | ✓ | /db-sql/ |
| **file_manager** | Файловый менеджер | FileMetadata | ✓ | /files/ |
| **kladr** | База КЛАДР | KladrAddress, KladrStreet | ✓ | - |

### Middleware:

| Middleware | Назначение |
|---|---|
| `komunal_dom.middleware.SubdomainMiddleware` | Обработка поддоменов (aspect.komunal-dom.ru) |
| `portal.middleware.AdminAccessMiddleware` | Контроль доступа к админке |

### Context Processors:

| Processor | Назначение |
|---|---|
| `portal.context_processors.admin_stats` | Статистика для админки |

---

## 3. URL ROUTING

### Главный routing (komunal_dom/urls.py):

| URL | App | Назначение |
|---|---|---|
| `/` | portal | Главная страница |
| `/admin/` | Django admin | Админка Django |
| `/logout/` | auth_views | Выход |
| `/files/` | file_manager | Файловый менеджер |
| `/chat/` | message_handler | Веб-чат с AI |
| `/llm-tester/` | llm_tester | LLM Tester |
| `/db-sql/` | database_viewer | СУБД SQL интерфейс |

### Дополнительные URLs (предположительно):

- `/subscribers/` - Личный кабинет жителей (portal)
- `/director/` - Кабинет директора (portal)
- `/admin-uk/` - Админка УК (portal)
- `/api/` - Внешнее API (если есть)

---

## 4. КЛЮЧЕВЫЕ ДИРЕКТОРИИ

### komunal_dom/ (главный проект)

```
komunal_dom/
├── settings.py              # Настройки Django
├── urls.py                  # Главный URL routing
├── wsgi.py                  # WSGI приложение (gunicorn)
├── middleware.py            # SubdomainMiddleware
└── __init__.py
```

### portal/ (основное приложение)

```
portal/
├── models.py                # AIPrompt, UserProfile, SemanticPattern, ServicesCatalog
├── views.py                 # Основные views (39KB - нужен рефакторинг!)
├── urls.py                  # URL routing для portal
├── admin.py                 # Админка УК
├── admin_views.py           # Views для админки
├── kladr_views.py           # Views для КЛАДР (why not in kladr app?)
├── ai_manager.py            # AI менеджер (старый?)
├── middleware.py            # AdminAccessMiddleware
├── context_processors.py    # Admin stats
├── templates/               # Шаблоны portal
└── migrations/              # Миграции portal
```

### message_handler/ (логирование сообщений)

```
message_handler/
├── models.py                # MessageLog, CommunicativeScript, APIErrorLog
├── views.py                 # Views для веб-чата
├── urls.py                  # URL routing для /chat/
├── templates/               # Шаблоны чата
└── migrations/              # Миграции
```

### llm_tester/ (тестирование промптов)

```
llm_tester/
├── models.py                # PromptTemplate, LLMRequestLog
├── views.py                 # Views для тестирования
├── urls.py                  # URL routing для /llm-tester/
├── admin.py                 # Админка для тестирования
└── management/              # Management команды
```

---

## 5. ПОДозРИТЕЛЬНЫЕ МЕСТА

### Неожиданное размещение:

1. **20+ AI-сервисов в корне** - почему не в отдельном app?
2. **kladr_views.py in portal/** - почему не in kladr/?
3. **ai_manager.py in portal/** - старый? Проверить использование
4. **migrations/** в корне - почему не в apps?

### Дублирование:

1. **doc/** и **docs/** - две директории документации
2. **SemanticPattern** (portal) vs **CommunicativeScript** (message_handler) - похожая функциональность
3. **AIPrompt** (portal) vs **PromptTemplate** (llm_tester) - два хранилища промптов

### Рудименты:

1. **old/** - 50+ старых файлов (очевидный рудимент)
2. **backups_20260223/** и **backups_20260223_133420/** - старые backup'ы
3. **migrations_fixes/** - временные fix'ы
4. **prompts_backup/** - бэкапы промптов (нужны ли?)

---

## 6. ГДЕ НАХОДЯТСЯ ENTRY POINTS

### Web:

- **Gunicorn:** `/etc/systemd/system/gunicorn-komunal-dom.service` → `komunal_dom/wsgi.py`
- **Nginx:** `/etc/nginx/sites-enabled/komunal-dom.ru` → прокси на gunicorn

### Telegram бот:

- **Systemd:** `/etc/systemd/system/enhanced-aspect-bot.service` → `enhanced_aspect_bot.py`

### CLI:

- **Django manage.py:** `./manage.py` (migrate, collectstatic, shell, runserver)
- **Management commands:** `*/management/commands/*.py`

---

## 7. СТАТИКА И МЕДИА

### Статические файлы:

- **Исходники:** `/var/www/komunal-dom_ru/static/`
- **Собранная статика:** `/var/www/komunal-dom_ru/staticfiles/`
- **Команда:** `./manage.py collectstatic`

### Медиа файлы:

- **Расположение:** `/var/www/komunal-dom_ru/media/`
- **URL:** `/media/`
- **Settings:** `MEDIA_ROOT`, `MEDIA_URL`

---

## 8. ЧТО НУЖНО ПРОВЕРИТЬ ВРУЧНУЮ

### Файлы:

1. `/var/www/komunal-dom_ru/portal/ai_manager.py` - используется ли?
2. `/var/www/komunal-dom_ru/portal/kladr_views.py` - почему не in kladr/?
3. `/var/www/komunal-dom_ru/old/*` - все файлы на удаление
4. `/var/www/komunal-dom_ru/scripts/*` - какие скрипты?

### Директории:

1. `/var/www/komunal-dom_ru/doc/` vs `/var/www/komunal-dom_ru/docs/` - объединить
2. `/var/www/komunal-dom_ru/prompts_backup/` - нужен ли?
3. `/var/www/komunal-dom_ru/migrations/` - что это за миграции?

### Модели:

1. **SemanticPattern** (portal) - используется ли? Вытеснен CommunicativeScript?
2. **AIPrompt** (portal) - дублирует PromptTemplate? Какой использовать?

---

## 9. РЕКОМЕНДАЦИИ ПО СТРУКТУРЕ

### Минимальные изменения:

1. **Удалить old/** - 50+ файлов освободят ~5MB
2. **Объединить doc/** и **docs/** - одна директория
3. **Архивировать старые backup'ы** - оставить только последние 3
4. **Удалить prompts_backup/** - если не используется

### Средние изменения:

1. **Создать ai_services/** - переместить 20+ AI файлов из корня
2. **Рефакторинг portal/views.py** - разбить на компоненты
3. **Унифицировать промпты** - объединить AIPrompt и PromptTemplate

### Сложные изменения:

1. **kladr_views.py → kladr/views.py** - переместить в свой app
2. **Убрать миграции из корня** - перенести в соответствующие apps
3. **Создать shared app** - для общих утилит

---

## 10. БЫСТРЫЙ ПОИСК ФАЙЛОВ

### Найти все Python файлы:

```bash
find /var/www/komunal-dom_ru -name "*.py" -type f ! -path "*/venv/*" ! -path "*/.git/*"
```

### Найти все models.py:

```bash
find /var/www/komunal-dom_ru -name "models.py" -type f
```

### Найти все views.py:

```bash
find /var/www/komunal-dom_ru -name "views.py" -type f
```

### Найти все admin.py:

```bash
find /var/www/komunal-dom_ru -name "admin.py" -type f
```

### Найти файлы больше 50KB:

```bash
find /var/www/komunal-dom_ru -name "*.py" -type f -size +50k ! -path "*/venv/*"
```

---

**ВЫВОД:** Проект имеет четкую модульную структуру (8 Django apps), но страдает от техдолга (old/, multiple backups) и architectural debt (20+ сервисов в корне, portal/views.py 39KB). Quick wins: удалить old/, объединить doc/docs/, архивировать старые backup'ы.
