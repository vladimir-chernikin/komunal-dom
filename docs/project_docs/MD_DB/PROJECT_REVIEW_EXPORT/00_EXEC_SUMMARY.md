# EXECUTIVE SUMMARY - Коммунальный Дом (komunal-dom.ru)

**Дата аудита:** 2026-03-19
**Проект:** komunal-dom.ru
**Тип:** Боевой Django-проект (УК "Аспект")
**Стек:** Django 6.0 + PostgreSQL 16 + gunicorn + nginx + Ubuntu

---

## 1. НАЗНАЧЕНИЕ ПРОЕКТА

**Бизнес:** Система для управляющей компании (УК "Аспект") по обработке обращений жителей.

**Основной сценарий:**
1. Житель пишет проблему в Telegram/WhatsApp/на сайт
2. AI-система определяет услугу из каталога (68 услуг)
3. Создается заявка для исполнителей
4. Операторы УК видят заявки в админке

**Подсистемы:**
- **AI-боты** (Telegram, WhatsApp, веб-чат)
- **Каталог услуг** (68 услуг, справочники)
- **Воронка точности** (TagSearch + VectorSearch + SemanticSearch + AI)
- **Логирование диалогов** (dialog_logs, MessageLog)
- **Админка УК** (управление заявками, пользователями)
- **НСИ** (справочники компаний, оборудования)
- **Файловый менеджер**
- **LLM Tester** (тестирование промптов)

**Ядро продукта:** AI-системы определения услуг (MainAgent + микросервисы поиска)

---

## 2. 10 САМЫХ ВАЖНЫХ ВЫВОДОВ

### Позитивные:

1. **Четкая модульность** - 8 Django apps с четким разделением ответственности
2. **Хорошая изоляция AI** - все AI-сервисы в корне проекта (20+ файлов)
3. **Единая точка входа** - MainAgent координирует все микросервисы
4. **Версионирование промптов** - PromptTemplate с версионированием (llm_tester)
5. **Детальное логирование** - MessageLog с метриками (LLM, токены, стоимость)

### Риски:

6. **20+ AI-сервисов в корне** - нет модульности, сложно поддерживать
7. **Дублирование документации** - doc/ и docs/ (2 папки)
8. **Три backup-директории** - backups/, backups_20260223/, backups_20260223_133420/
9. **Директория old/** - 50+ старых файлов (рудимент техдолга)
10. **Смешивание слоев** - portal/views.py 39KB (нужно рефакторинг)

---

## 3. ГЛАВНЫЕ РИСКИ

### Operational Risks:

- **Gunicorn workers кешируют код** - после изменений .py нужен restart (часто забывают)
- **Нет автоматизированного деплоя** - ручной деплой, высокий риск ошибок
- **Множественные backup'ы** - неясно, какие актуальные

### Architecture Risks:

- **20+ сервисов в корне** - нет модульности, сложная навигация
- **Portal/views.py 39KB** - нужен рефакторинг на компоненты
- **Unmanaged модели** - services_catalog управляется вне Django (риск рассинхрона)

### Code Quality Risks:

- **old/** - 50+ старых файлов (нужно удалить или архивировать)
- **Дублирование** - SemanticPattern (portal) и CommunicativeScript (message_handler)
- **Множественные промежуточные миграции** - migrations/ и migrations_fixes/

---

## 4. ГЛАВНЫЕ РУДИМЕНТЫ

### Явные рудименты (можно удалить):

1. **old/** - 50+ старых версий ботов и скриптов
2. **doc/** и **docs/** - дублирующие директории документации
3. **backups_20260223/** и **backups_20260223_133420/** - старые backup'ы
4. **migrations_fixes/** - временные fix'ы (можно перенести в git history)

### Потенциальные рудименты (нужна проверка):

1. **prompts_backup/** - бэкапы промптов (нужны ли?)
2. **ai_manager.py** (portal) - старый AI менеджер? Проверить использование
3. **SemanticPattern** (portal) - вытесняется CommunicativeScript?
4. **kladr_views.py** (portal) - отдельный views для КЛАДР (why not in kladr app?)

---

## 5. ЧТО СМОТРЕТЬ СНАЧАЛА

### Критические файлы (приоритет 1):

1. `/var/www/komunal-dom_ru/main_agent.py` - главный координатор AI
2. `/var/www/komunal-dom_ru/message_handler_service.py` - обработка сообщений
3. `/var/www/komunal-dom_ru/portal/views.py` - основные views (39KB, нужен рефакторинг)
4. `/var/www/komunal-dom_ru/komunal_dom/settings.py` - настройки
5. `/var/www/komunal-dom_ru/message_handler/models.py` - MessageLog, CommunicativeScript

### AI/Поиск (приоритет 2):

6. `/var/www/komunal-dom_ru/ai_agent_service.py` - AI агент
7. `/var/www/komunal-dom_ru/vector_search_service.py` - векторный поиск
8. `/var/www/komunal-dom_ru/tag_search_service.py` - поиск по тегам
9. `/var/www/komunal-dom_ru/filter_detection_service.py` - детекция фильтров

### Runtime (приоритет 3):

10. `/etc/systemd/system/gunicorn-komunal-dom.service` - gunicorn сервис
11. `/etc/systemd/system/enhanced-aspect-bot.service` - Telegram бот
12. `/var/www/komunal-dom_ru/.env` - секреты (DB, API ключи)

---

## 6. СЛЕДУЮЩИЕ ШАГИ ДЛЯ УЛУЧШЕНИЯ

### Минимальные (быстрый эффект):

1. **Удалить old/** - 50+ файлов освободят ~5MB и уберут путаницу
2. **Объединить doc/** и **docs/** - одна директория документации
3. **Архивировать старые backup'ы** - оставить только последние 3
4. **Удалить prompts_backup/** - если не используется

### Средние (требуют тестирования):

1. **Рефакторинг portal/views.py** - разбить на компоненты (views/*.py)
2. **Создать ai_services/** - переместить 20+ AI файлов из корня
3. **Унифицировать промпты** - объединить AIPrompt и PromptTemplate

### Сложные (требуют архитектуры):

1. **Версионирование БД** - миграции для services_catalog (unmanaged)
2. **Автоматизированный деплой** - CI/CD пайплайн
3. **Мониторинг** - Prometheus/Grafana для production

---

## 7. СТАТИСТИКА ПРОЕКТА

| Метрика | Значение |
|---|---|
| Django apps | 8 |
| Python сервисы в корне | 20+ |
| Models | 15+ |
| URL endpoints | 20+ |
| Systemd сервисов | 2 (gunicorn + bot) |
| Backup директорий | 3 |
| Старых файлов (old/) | 50+ |
| Размер portal/views.py | 39KB |

---

## 8. АРХИТЕКТУРНЫЕ РЕШЕНИЯ

### Хорошие решения:

- ✅ Unmanaged модель для services_catalog (не ломает существующую БД)
- ✅ Единая точка входа (MainAgent)
- ✅ Версионирование промптов (PromptTemplate)
- ✅ Детальное логирование (MessageLog с metadata)
- ✅ Разделение на Django apps

### Проблемные решения:

- ❌ 20+ AI-сервисов в корне (нет модульности)
- ❌ portal/views.py 39KB (God Object)
- ❌ Дублирование (SemanticPattern vs CommunicativeScript)
- ❌ old/ не удалена (техдолг)

---

## 9. ДЛЯ КЛАУДА (AI-РЕВЬЮЕР)

**Чего Claude НЕ должен делать:**
- ❌ Менять .env без подтверждения
- ❌ Перезапускать gunicorn как первое действие
- ❌ Удалять файлы без проверки git status
- ❌ Применять миграции без backup'а БД
- ❌ Менять данные в БД (services_catalog) без разрешения

**Чего Claude ДОЛЖЕН делать:**
- ✅ Собрать факты (git status, systemctl status)
- ✅ Проверить изменения (git diff, git diff --staged)
- ✅ Понять контекст (прочитать файлы)
- ✅ Создать план действий
- ✅ Коммитить после каждого изменения
- ✅ Перезапускать gunicorn после изменений .py файлов
- ✅ Устанавливать права на новые файлы (chmod 644, chown olga:www-data)

---

## 10. КЛЮЧЕВЫЕ ФАЙТЫ ДЛЯ КОД-РЕВЬЮ

Если внешний ревьюер ограничен во времени, смотреть в этом порядке:

1. `main_agent.py` - главный координатор
2. `message_handler_service.py` - обработка сообщений
3. `portal/views.py` - нужен рефакторинг
4. `message_handler/models.py` - логирование
5. `komunal_dom/settings.py` - настройки
6. `ai_agent_service.py` - AI агент
7. `vector_search_service.py` - векторный поиск
8. `filter_detection_service.py` - детекция фильтров
9. `portal/admin.py` - админка УК
10. `komunal_dom/urls.py` - URL routing

---

**ВЫВОД:** Проект функционален, но нуждается в рефакторинге для улучшения поддерживаемости. Главные проблемы: техдолг (old/, multiple backups) и архитектурные (20+ сервисов в корне, portal/views.py 39KB). Quick wins: удалить old/, объединить doc/docs/, архивировать старые backup'ы.
