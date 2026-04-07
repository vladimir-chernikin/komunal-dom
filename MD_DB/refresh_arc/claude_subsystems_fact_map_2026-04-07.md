# ФАКТИЧЕСКАЯ КАРТА ПОДСИСТЕМ komunal-dom.ru

## 1. AI ЧАТ-БОТ ПРИЕМА ЗАЯВОК `/chat/`

**Назначение:** Веб-чат с AI для классификации и приема заявок от жителей

**URL / entry points:**
- `/chat/` - веб-чат (message_handler.urls:15)
- `/chat/api/send/` - отправка сообщения
- `/chat/api/external/` - внешнее API для интеграций
- `/chat/api/history/` - история чата
- `/chat/api/dialogs-list/` - список диалогов
- `/chat/api/performance-report/` - отчет о производительности

**Основные Django apps / внешние сервисы:**
- `message_handler` (Django app)
- `ai_agent_service.py` - AI-агент
- `filter_detection_service.py` - детекция фильтров
- `vector_search_service.py` - векторный поиск
- `tag_search_service.py` - теговый поиск
- `address_extractor_service.py` - извлечение адреса
- `dialog_logger_service.py` - логирование диалогов
- `communicative_scripts_service.py` - скрипты бота
- GigaChat API (внешний LLM провайдер)

**Ключевые файлы:**
- `message_handler/views.py` - веб-чат и API
- `message_handler/models.py` - MessageLog (dialog_logs), CommunicativeScript, APIErrorLog
- `ai_agent_service.py` - основной AI агент
- `filter_detection_service.py` - детекция инцидентов
- `main_agent.py` - оркестратор

**Таблицы БД:**
- `dialog_logs` - сообщения всех каналов (6728 записей)
- `message_handler_communicativescript` - скрипты бота
- `message_handler_apierrorlog` - ошибки API
- `ai_models` - модели AI (активные)
- `ai_providers` - провайдеры AI
- `llm_request_log` - логи LLM запросов
- `llm_response_cache` - кэш ответов

**Пересечения с другими подсистемами:**
- → `work_orders` - создание заявок через RequestIntake
- → `portal` - использует AIPrompt, ServicesCatalog
- → `nsi` - использует Company

**Статус:** **CORE** (основная бизнес-функция)

---

## 2. НОРМАТИВНЫЙ КОНСУЛЬТАНТ `/regulatory-chat/`

**Назначение:** AI-консультант по нормативным документам ЖКХ

**URL / entry points:**
- `/regulatory-chat/` - страница нормативного чата (portal.urls:18)
- Использует тот же AI-стек, но другие промпты

**Основные Django apps / внешние сервисы:**
- `portal` (Django app - view regulatory_chat)
- `ai_agent_service.py` - общий AI-агент
- Те же LLM провайдеры (GigaChat)

**Ключевые файлы:**
- `portal/views.py:117` - regulatory_chat()
- `portal/templates/portal/normative_chat.html`

**Таблицы БД:**
- `portal_aiprompt` - промпты (type='system', 'greeting', etc.)
- `dialog_logs` - общие логи (channel='web' или отдельный)
- `ai_models`, `ai_providers` - общие с chat/

**Пересечения с другими подсистемами:**
- ← `chat/` - общий AI-стек
- ← `portal` - общие промпты

**Статус:** **CORE** (отдельная бизнес-функция)

---

## 3. LLM TESTER `/llm-tester/`

**Назначение:** Тестирование и версионирование промптов для AI

**URL / entry points:**
- `/llm-tester/` - дашборд
- `/llm-tester/prompts/` - база промптов
- `/llm-tester/test/<slug>/` - тестирование промпта
- `/llm-tester/api/send-request/` - отправка в LLM
- `/llm-tester/api/update-template/` - обновление шаблона
- `/llm-tester/api/save-preset/` - сохранение пресета
- `/llm-tester/results/` - результаты тестов

**Основные Django apps / внешние сервисы:**
- `llm_tester` (Django app)
- LLM провайдеры (GigaChat, OpenAI, etc.)

**Ключевые файлы:**
- `llm_tester/views.py` - все view
- `llm_tester/models.py` - PromptTemplate, PromptPreset, LLMTestResult

**Таблицы БД:**
- `llm_tester_prompttemplate` - 7 активных шаблонов
- `llm_tester_promptpreset` - пресеты настроек
- `llm_tester_llmtestresult` - результаты тестов
- `prompt_template_versions` - версии шаблонов
- `prompt_templates` - общие шаблоны (4 активных)

**Пересечения с другими подсистемами:**
- ← `chat/` - использует те же промпты
- ← `regulatory-chat/` - использует те же промпты

**Статус:** **SUPPORT** (инструмент разработки)

---

## 4. ТРАССИРОВКА ДИАЛОГОВ `/admin-uk/dialog-trace/`

**Назначение:** Диагностика и отладка AI-диалогов

**URL / entry points:**
- `/admin-uk/dialog-trace/` - UI трассировки
- `/admin-uk/dialog-trace/<filename>/` - отчет по диалогу
- `/api/dialog-trace/` - API трассировки
- `/api/dialog-sessions/` - API сессий
- `/api/dialog-reports/` - API отчетов
- `/api/dialog-full-trace/` - API полного trace

**Основные Django apps / внешние сервисы:**
- `portal` (Django app - admin_views)
- `dialog_trace_service.py` - сервис трассировки
- `trace_report_service.py` - генерация отчетов

**Ключевые файлы:**
- `portal/views.py:131-200` - dialog_trace_page, dialog_trace_api
- `dialog_trace_service.py`
- `trace_report_service.py`

**Таблицы БД:**
- `dialog_logs` - основной источник данных
- `debug_trace_log` - отладочные логи (если есть)
- `debug_span_log` - спаны трассировки

**Пересечения с другими подсистемами:**
- ← `chat/` - использует их dialog_logs
- ← `regulatory-chat/` - использует их dialog_logs

**Статус:** **SUPPORT** (диагностика)

---

## 5. СИСТЕМА УПРАВЛЕНИЯ ЗАЯВКАМИ `work_orders/`

**Назначение:** Управление жизненным циклом заявок ЖКХ

**URL / entry points:**
- `/work_orders/executor/` - дашборд исполнителя
- `/work_orders/executor/my-requests/` - мои заявки
- `/work_orders/executor/pool/` - пул подразделения
- `/work_orders/contractor/` - дашборд подрядчика
- `/work_orders/request/<id>/` - карточка заявки
- `/work_orders/create/` - создание заявки
- `/work_orders/management/` - управленческий список
- `/work_orders/resident/` - дашборд жителя
- `/work_orders/api/<id>/take/` - взять в работу
- `/work_orders/api/<id>/start/` - начать работу
- `/work_orders/api/<id>/complete/` - завершить
- `/work_orders/api/<id>/close/` - закрыть

**Основные Django apps / внешние сервисы:**
- `work_orders` (Django app)
- Django ORM (request_mgmt schema)

**Ключевые файлы:**
- `work_orders/views.py` - все view (ExecutorDashboardView, ContractorDashboardView, etc.)
- `work_orders/models.py` - 15 моделей в request_mgmt schema
- `work_orders/templates/work_orders/` - шаблоны

**Таблицы БД (schema request_mgmt):**
**Справочники:**
- `route_ref` - типовые маршруты
- `company_department` - подразделения (иерархия)
- `contractor_organization` - подрядчики
- `company_route_mapping` - маппинг маршрутов
- `work_order_status_ref` - статусы заявок
- `work_order_status_transition` - переходы статусов
- `sla_policy` - SLA политики

**Основные сущности:**
- `work_order` - заявки (главная таблица)
- `request_intake` - входящие события
- `work_order_status_history` - история статусов
- `sla_instance` - SLA экземпляры
- `work_order_event_log` - журнал событий
- `work_order_attachment` - вложения
- `notification_outbox` - уведомления

**Пересечения с другими подсистемами:**
- ← `chat/` - создает заявки через RequestIntake
- → `portal` - использует ServicesCatalog, ServiceObject
- → `nsi` - использует Company

**Статус:** **CORE** (основная бизнес-функция)

---

## 6. LEGACY ROUTES `/executor/` (В portal/urls.py)

**Назначение:** Устаревшие маршруты исполнителя (сохранены для обратной совместимости)

**URL / entry points:**
- `/executor/` - старый дашборд исполнителя
- `/executor/take/<id>/` - взять заявку
- `/executor/arrived/<id>/` - прибытие
- `/executor/complete/<id>/` - завершение
- `/executor/upload-photo/<id>/` - загрузка фото
- `/executor/report/<id>/` - отчет

**Основные Django apps:**
- `portal` (Django app - views.py:192-240)

**Ключевые файлы:**
- `portal/views.py:192-240` - legacy функции executor_*

**Таблицы БД:**
- `bot_service_requests` - старые заявки бота (legacy)

**Пересечения с другими подсистемами:**
- → `work_orders/` - перенаправляет на новую систему

**Статус:** **LEGACY** (устаревшее, используется для обратной совместимости)

---

## 7. SQL ИНТЕРФЕЙС `/db-sql/`

**Назначение:** Веб-интерфейс для выполнения SQL запросов к БД

**URL / entry points:**
- `/db-sql/` - список таблиц
- `/db-sql/structure/` - структура таблицы
- `/db-sql/data/` - данные таблицы
- `/db-sql/relations/` - ER диаграмма

**Основные Django apps:**
- `database_viewer` (Django app)

**Ключевые файлы:**
- `database_viewer/views.py` - все view
- `database_viewer/templates/database_viewer/`

**Таблицы БД:**
- Все таблицы (read-only доступ через information_schema)

**Пересечения с другими подсистемами:**
- ← Все подсистемы - показывает их данные

**Статус:** **SUPPORT** (инструмент администратора)

---

## 8. ПОРТАЛ / РОЛИ / КАБИНЕТЫ `portal/`

**Назначение:** Сквозной слой для аутентификации, авторизации и маршрутизации пользователей

**URL / entry points:**
- `/` - landing page
- `/login/` - кастомный login
- `/subscribers/` - кабинет жителя
- `/chief-engineer/` - кабинет главного инженера
- `/director/` - кабинет директора
- `/director/residents/` - управление жителями
- `/director/departments/` - управление подразделениями
- `/admin-uk/` - админка УК
- `/admin-uk/prompts/` - управление промптами
- `/admin-uk/kladr/` - управление КЛАДР

**Основные Django apps:**
- `portal` (Django app)
- Django Auth (User)

**Ключевые файлы:**
- `portal/views.py` - все view (2000+ строк)
- `portal/models.py` - UserProfile, AIPrompt, SemanticPattern
- `portal/mixins.py` - get_primary_membership
- `portal/middleware.py` - CompanyMembershipMiddleware, DjangoAdminProtectionMiddleware
- `templates/portal/` - шаблоны всех кабинетов

**Таблицы БД (public schema):**
- `portal_userprofile` - профили (role: uk_user, direktor_uk, executor, resident)
- `portal_aiprompt` - промпты бота
- `portal_semanticpattern` - семантические паттерны
- `auth_user` - пользователи Django
- `django_session` - сессии

**Пересечения с другими подсистемами:**
- → Все подсистемы - аутентификация и авторизация
- → `work_orders/` - primary_company, primary_department
- → `nsi` - компании

**Статус:** **CORE** (сквозной слой)

---

## 9. НСИ - НОРМАТИВНО-СПРАВОЧНАЯ ИНФОРМАЦИЯ `nsi/`

**Назначение:** Справочники компаний, оборудования, категорий услуг

**URL / entry points:**
- `/admin/` - Django admin (основной интерфейс НСИ)
- Нет кастомных URL (только через Django admin)

**Основные Django apps:**
- `nsi` (Django app)
- Django Admin

**Ключевые файлы:**
- `nsi/models.py` - Company, EquipmentType, RefCategory, RefServiceType, RefLocalization, RefRoute, RefPricingUnit
- `nsi/admin.py` - регистрация в Django admin

**Таблицы БД:**
- `nsi_company` - компании
- `nsi_equipmenttype` - виды оборудования
- `ref_categories` - категории услуг
- `ref_service_types` - типы услуг (Инцидент/Запрос)
- `ref_localization` - локализации (Общедомовое/Индивидуальное)
- `ref_routes` - маршруты
- `ref_pricing_units` - единицы ценообразования

**Пересечения с другими подсистемами:**
- → `work_orders/` - использует Company
- → `portal/` - использует Company в UserProfile
- ← Все подсистемы - используют справочники

**Статус:** **SUPPORT** (справочные данные)

---

## 10. FILE MANAGER `/files/`

**Назначение:** Управление файлами пользователей

**URL / entry points:**
- `/files/` - файловый менеджер

**Основные Django apps:**
- `file_manager` (Django app)

**Ключевые файлы:**
- `file_manager/views.py`
- `file_manager/models.py` - UserFile

**Таблицы БД:**
- `file_manager_userfile` - файлы пользователей

**Пересечения с другими подсистемами:**
- ← `work_orders/` - вложения к заявкам

**Статус:** **SUPPORT** (вспомогательная функция)

---

## 11. КЛАДР `kladr/`

**Назначение:** Справочник адресов (КЛАДР)

**URL / entry points:**
- `/admin-uk/kladr/` - управление КЛАДР
- `/admin-uk/kladr/objects/` - объекты
- `/admin-uk/kladr/buildings/` - здания
- `/admin-uk/kladr/service-areas/` - зоны обслуживания
- `/api/kladr/search/` - поиск адреса

**Основные Django apps:**
- `kladr` (Django app)

**Ключевые файлы:**
- `kladr/models.py` - KladrAddressObject, Building, ServiceArea, KladrDataImportLog
- `portal/kladr_views.py` - UI КЛАДР

**Таблицы БД:**
- `kladr_kladraddressobject` - адресные объекты
- `kladr_building` - здания
- `kladr_servicearea` - зоны обслуживания
- `kladr_servicearea_buildings` - связь зданий с зонами
- `kladr_kladrobjecttype` - типы объектов
- `kladr_dataimportlog` - логи импорта

**Пересечения с другими подсистемами:**
- → `chat/` - используется для извлечения адреса
- → `work_orders/` - используется в заявках

**Статус:** **SUPPORT** (справочник адресов)

---

# ТАБЛИЦЫ AI И ПОИСКА: ЧТО РЕАЛЬНО ИСПОЛЬЗУЕТСЯ

## 1. AI ИНФРАСТРУКТУРА

**АКТИВНО ИСПОЛЬЗУЕТСЯ:**
- `ai_models` - модели AI (пруф: message_handler использует AIAgentService)
- `ai_providers` - провайдеры AI (GigaChat, etc.)
- `ai_request_history` - история запросов к AI
- `ai_cost_tracking` - отслеживание затрат
- `ai_model_pricing` - ценообразование моделей
- `ai_type_of_service` - типы обслуживания AI

**Пруфы:**
```python
# ai_agent_service.py импортируется в 44 файлах
# message_handler/views.py использует AI-агента
# llm_tester использует LLM провайдеров
```

---

## 2. ЛОГИРОВАНИЕ DIALOGS

**АКТИВНО ИСПОЛЬЗУЕТСЯ:**
- `dialog_logs` - 6728 записей, все каналы (telegram, web, test_bot, api)
- `llm_request_log` - логи LLM запросов

**Пруфы:**
```sql
SELECT COUNT(*) as cnt, channel FROM dialog_logs GROUP BY channel;
-- 2652 web, 2474 test_bot, 705 telegram, 209 api
```

---

## 3. ПОИСК УСЛУГ

**АКТИВНО ИСПОЛЬЗУЕТСЯ:**
- `services_catalog` - каталог услуг (основной справочник)
- `ref_tags_embeddings` - векторные вложения тегов (jsonb)
- `portal_semanticpattern` - семантические паттерны (ключевые слова)

**ПОД ВОПРОСОМ (нужно проверить):**
- `service_objects` - объекты обслуживания (используется в work_orders)
- `service_tags_backup` - бэкап тегов (выглядит как legacy)
- `services_catalog_backup` - бэкап каталога (legacy)
- `services_catalog_old` - старая версия (legacy)

**Пруфы:**
```python
# work_orders/models.py:580 - service ForeignKey на ServicesCatalog
# vector_search_service.py - использует ref_tags_embeddings
# filter_detection_service.py - использует portal_semanticpattern
```

---

## 4. ПРОМПТЫ

**АКТИВНО ИСПОЛЬЗУЕТСЯ:**
- `portal_aiprompt` - промпты для бота (system, greeting, error, etc.)
- `prompt_templates` - общие шаблоны (4 активных)
- `prompt_template_versions` - версии шаблонов
- `llm_tester_prompttemplate` - тестовые шаблоны (7 активных)
- `llm_tester_promptpreset` - пресеты настроек

**Пруфы:**
```sql
SELECT COUNT(*) FROM llm_tester_prompttemplate WHERE is_active = true; -- 7
SELECT COUNT(*) FROM prompt_templates WHERE is_active = true; -- 4
```

---

## 5. ДИАГНОСТИКА

**АКТИВНО ИСПОЛЬЗУЕТСЯ:**
- `debug_trace_log` - логи трассировки (используется dialog_trace_service.py)
- `debug_span_log` - спаны трассировки

**Пруфы:**
```python
# portal/views.py:131 - dialog_trace_page использует debug_trace_log
```

---

## 6. LEGACY / НЕИСПОЛЬЗУЕМОЕ

**ВЫГЛЯДИТ КАК LEGACY:**
- `bot_service_requests` - старые заявки бета-бота (используется в legacy routes)
- `bot_service_requests_backup` - бэкап (legacy)
- `service_tags_backup` - бэкап тегов (legacy)
- `services_catalog_backup` - бэкап каталога (legacy)
- `services_catalog_before_fk_restore` - бэкап перед восстановлением FK (legacy)
- `services_catalog_old` - старая версия (legacy)
- `tmpoldadres` - временная таблица (legacy)

**Пруфы:**
```python
# portal/views.py:192-240 - legacy executor routes используют bot_service_requests
# Наличие "_backup", "_old", "tmp" в названиях
```

---

# ПРЕДВАРИТЕЛЬНАЯ СХЕМА ДЕКОМПОЗИЦИИ ПО ПОДСИСТЕМАМ

## СЛОЙ 1: CORE БИЗНЕС-ФУНКЦИИ

**1. AI Чат-бот приема заявок** (`/chat/`)
- Ответственность: классификация обращений, создание заявок
- Зависимости: AI-сервисы, КЛАДР, НСИ
- Выходы: заявки в work_orders

**2. Нормативный консультант** (`/regulatory-chat/`)
- Ответственность: консультирование по нормативам ЖКХ
- Зависимости: AI-сервисы, промпты
- Выходы: ответы пользователю

**3. Управление заявками** (`/work_orders/`)
- Ответственность: жизненный цикл заявок, SLA, маршрутизация
- Зависимости: НСИ, portal (профили)
- Выходы: выполненные заявки, уведомления

---

## СЛОЙ 2: СКВОЗНЫЕ СЕРВИСЫ

**4. Портал / Роли / Кабинеты** (`portal/`)
- Ответственность: аутентификация, авторизация, маршрутизация
- Зависимости: Django Auth
- Выходы: контекст пользователя для всех подсистем

**5. НСИ - Справочники** (`nsi/`)
- Ответственность: справочные данные (компании, оборудование, категории)
- Зависимости: нет
- Выходы: справочники для всех подсистем

---

## СЛОЙ 3: AUXILIARY

**6. LLM Tester** (`/llm-tester/`)
- Ответственность: тестирование и версионирование промптов
- Зависимости: AI-провайдеры
- Выходы: улучшенные промпты для chat/ и regulatory-chat/

**7. Трассировка диалогов** (`/admin-uk/dialog-trace/`)
- Ответственность: диагностика AI-диалогов
- Зависимости: dialog_logs
- Выходы: отчеты для разработчиков

**8. SQL Интерфейс** (`/db-sql/`)
- Ответственность: веб-доступ к БД
- Зависимости: все таблицы
- Выходы: данные для админа

**9. File Manager** (`/files/`)
- Ответственность: управление файлами
- Зависимости: work_orders
- Выходы: вложения к заявкам

**10. КЛАДР** (`kladr/`)
- Ответственность: справочник адресов
- Зависимости: внешние данные КЛАДР
- Выходы: адреса для chat/ и work_orders/

---

## СЛОЙ 4: LEGACY

**11. Legacy Routes** (`/executor/` в portal/)
- Ответственность: обратная совместимость
- Зависимости: bot_service_requests
- Выходы: перенаправление на /work_orders/

---

# КРИТИЧЕСКИЕ ПЕРЕСЕЧЕНИЯ

1. **dialog_logs** ← chat/, regulatory-chat/, dialog-trace/
2. **ai_models + ai_providers** ← chat/, regulatory-chat/, llm-tester/
3. **portal_aiprompt** ← chat/, regulatory-chat/
4. **services_catalog** ← work_orders/, chat/
5. **nsi_company** ← work_orders/, portal/, chat/
6. **portal_userprofile** ← все подсистемы (аутентификация)

---

**Это ФАКТИЧЕСКАЯ карта на основе кода, БД и runtime. Без предположений из MD_DB.**
