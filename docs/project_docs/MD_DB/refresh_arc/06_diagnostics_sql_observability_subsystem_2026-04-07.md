# Подсистема: Диагностика / SQL-интерфейс / observability / служебные инструменты

Дата: 2026-04-07

## Назначение

Это не одна бизнес-подсистема, а инженерный support-контур:
- просмотр БД;
- трассировка диалогов;
- генерация отчетов;
- LLM tester;
- file manager;
- частично КЛАДР-инструменты.

Ниже перечислены именно те инженерные блоки, которые уже живут в проекте и помогают сопровождать основные подсистемы.

## 1. SQL-интерфейс `/db-sql/`

### Назначение

- просмотр таблиц;
- просмотр структуры;
- просмотр данных;
- просмотр связей.

### Файлы

- [database_viewer/views.py](/var/www/komunal-dom_ru/database_viewer/views.py)
- [database_viewer/urls.py](/var/www/komunal-dom_ru/database_viewer/urls.py)
- [database_viewer/templates/database_viewer/](/var/www/komunal-dom_ru/database_viewer/templates/database_viewer)

### Важный технический факт

Описания таблиц берутся из PostgreSQL comments:
- `obj_description((schema||'.'||table)::regclass, 'pg_class')`

Следствие:
- если описания не видны на `/db-sql/`, чинить надо не шаблон, а PostgreSQL metadata.

## 2. Диалоговая трассировка

### Назначение

- просмотр сессий;
- просмотр сообщений;
- просмотр metadata;
- генерация и чтение markdown-отчетов по диалогам.

### Файлы

- [portal/views.py](/var/www/komunal-dom_ru/portal/views.py)
- [dialog_trace_service.py](/var/www/komunal-dom_ru/dialog_trace_service.py)
- [trace_report_service.py](/var/www/komunal-dom_ru/trace_report_service.py)

### Таблицы

- `dialog_logs`
- `llm_request_log`

### Артефакты

- отчеты пишутся в `/tmp/`

## 3. LLM Tester

### Назначение

- инженерное тестирование шаблонов и ответов LLM;
- не пользовательская бизнес-функция.

### Таблицы

- `llm_tester_prompttemplate`
- `llm_tester_promptpreset`
- `llm_tester_llmtestresult`

### Файлы

- [llm_tester/models.py](/var/www/komunal-dom_ru/llm_tester/models.py)
- [llm_tester/views.py](/var/www/komunal-dom_ru/llm_tester/views.py)
- [llm_tester/urls.py](/var/www/komunal-dom_ru/llm_tester/urls.py)

## 4. File Manager

### Назначение

- загрузка, скачивание и удаление пользовательских файлов;
- административная и пользовательская служебная функция.

### Файлы

- [file_manager/models.py](/var/www/komunal-dom_ru/file_manager/models.py)
- [file_manager/views.py](/var/www/komunal-dom_ru/file_manager/views.py)
- [file_manager/urls.py](/var/www/komunal-dom_ru/file_manager/urls.py)

### Таблица

- `file_manager_userfile`

### Текущее состояние

- модель и UI живые;
- таблица сейчас пустая.

## 5. КЛАДР-инструменты

### Назначение

- административная работа с адресными объектами, зданиями и зонами обслуживания.

### Точки входа

- `/admin-uk/kladr/...`

### Таблицы

- `kladr_kladraddressobject`
- `kladr_kladrobjecttype`
- `kladr_building`
- `kladr_servicearea`
- `kladr_dataimportlog`
- `kladr_servicearea_buildings`

### Текущее состояние

- модели, views и шаблоны живые;
- данные в таблицах пока пустые.

Это значит:
- КЛАДР-подсистема пока скорее "подключена, но не заселена".

## 6. Что считать support-слоем проекта

К support/engineering contour на сегодня логично отнести:
- `database_viewer`
- `llm_tester`
- dialog trace / trace reports
- `file_manager`
- admin-side KLADR tools

Эти блоки не должны смешиваться с:
- доменной моделью АДС;
- бизнес-логикой AI чатбота;
- внешним нормативным консультантом.

## 7. Почему это важно для будущего разведения по схемам

Если потом раскладывать таблицы по схемам PostgreSQL, support-контур удобно отделять от core business контуров:

- `chatbot/ai runtime`
- `ads/work_orders`
- `nsi/identity/catalog`
- `support/diagnostics/admin tools`

Именно этот документ нужен, чтобы не свалить в одну схему:
- логи;
- тестовые таблицы;
- админские инструменты;
- рабочие бизнес-сущности.

