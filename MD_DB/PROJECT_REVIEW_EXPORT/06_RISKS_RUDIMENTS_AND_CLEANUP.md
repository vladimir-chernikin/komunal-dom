# RISKS_RUDIMENTS_AND_CLEANUP - Коммунальный Дом

**Дата:** 2026-03-19

---

## 1. НАБЛЮДАЕМЫЕ РИСКИ

### Operational Risks (эксплуатационные):

#### Риск 1: Забыли перезапустить gunicorn

**Проблема:** Gunicorn workers кешируют Python код в памяти

**Последствия:**
- Изменения .py файлов не применяются
- Пользователи видят старый код
- Путаница при разработке

**Частота:** Высокая (было 5+ случаев)

**Митигация:**
- ✅ Добавить чек-лист в CLAUDE.md
- ✅ Обязательный restart после изменений .py
- ✅ Проверка статуса после restart

#### Риск 2: Нет автоматизированного деплоя

**Проблема:** Ручной деплой, высокий риск ошибок

**Последствия:**
- Человеческий фактор
- Пропущенные шаги (migrate, collectstatic, restart)
- Потеря данных

**Частота:** Средняя

**Митигация:**
- ⚠️ Разработать чек-лист деплоя
- ⚠️ Добавить автоматические бэкапы перед миграциями
- ⚠️ Рассмотреть CI/CD в будущем

#### Риск 3: Множественные backup'ы без ротации

**Проблема:** 3 backup директории, неясно какие актуальные

**Последствия:**
- Смешение актуальных и устаревших бэкапов
- Потеря дискового пространства
- Путаница при восстановлении

**Частота:** Средняя

**Митигация:**
- ✅ Оставить только последние 3 бэкапа
- ✅ Архивировать старые
- ✅ Добавить cron для автоматических бэкапов

### Architecture Risks (архитектурные):

#### Риск 4: 20+ AI-сервисов в корне

**Проблема:** Нет модульности, сложно поддерживать

**Последствия:**
- Сложная навигация
- Трудно найти нужный сервис
- Нет четкой структуры

**Частота:** Высокая

**Митигация:**
- ⚠️ Создать ai_services/ директорию
- ⚠️ Сгруппировать по функциональности
- ⚠️ Добавить __init__.py с описанием

#### Риск 5: Portal/views.py 39KB

**Проблема:** God Object, нужен рефакторинг

**Последствия:**
- Сложно понимать
- Сложно тестировать
- Сложно поддерживать

**Частота:** Средняя

**Митигация:**
- ⚠️ Разбить на компоненты (views/*.py)
- ⚠️ Выделить логику в сервисы
- ⚠️ Добавать type hints

#### Риск 6: Unmanaged модели

**Проблема:** ServicesCatalog не управляется Django

**Последствия:**
- Риск рассинхрона с реальной БД
- Нет миграций
- Сложно версионировать

**Частота:** Низкая

**Митигация:**
- ⚠️ Добавить миграции для версионирования
- ⚠️ Рассмотреть managed=True
- ⚠️ Добавить проверки целостности

### Code Quality Risks:

#### Риск 7: Дублирование промптов

**Проблема:** AIPrompt (portal) vs PromptTemplate (llm_tester)

**Последствия:**
- Неясно, какой использовать
- Рассинхрон промптов
- Путаница при разработке

**Частота:** Средняя

**Митигация:**
- ⚠️ Унифицировать промпты
- ⚠️ Оставить один (предпочтительно PromptTemplate)
- ⚠️ Мигрировать данные

#### Риск 8: SemanticPattern vs CommunicativeScript

**Проблема:** Похожая функциональность

**Последствия:**
- Дублирование кода
- Неясно, какой использовать
- Путаница при разработке

**Частота:** Средняя

**Митигация:**
- ✅ Проверить использование SemanticPattern
- ✅ Если не используется - удалить
- ✅ Если используется - четко разделить

### Integration Risks:

#### Риск 9: Зависимость от внешних API

**Проблема:** YandexGPT, Yandex Embeddings API

**Последствия:**
- Если API недоступен - AI не работает
- Нет fallback механизма
- Нет мониторинга доступности

**Частота:** Низкая

**Митигация:**
- ⚠️ Добавить fallback механизмы
- ⚠️ Добавить мониторинг доступности
- ⚠️ Рассмотреть кеширование результатов

#### Риск 10: Нет изоляции внешних API

**Проблема:** Прямые HTTP запросы в AIAgentService

**Последствия:**
- Сложно тестировать
- Сложно менять провайдера
- Нет единообразия

**Частота:** Средняя

**Митигация:**
- ⚠️ Создать адаптеры для внешних API
- ⚠️ Добавить интерфейсы
- ⚠️ Внедрить IoC контейнер

---

## 2. РУДИМЕНТЫ (ТОЧНЫЕ)

### Явные рудименты (можно удалить):

#### old/

**Расположение:** `/var/www/komunal-dom_ru/old/`

**Размер:** 50+ файлов (~5MB)

**Содержимое:**
- 50+ старых версий ботов (address_bot_*.py)
- Старые скрипты (add_test_services.py, analyze_*.py)
- Старая документация (*.md)
- Временные файлы (check_*.py)

**Рекомендация:** Удалить или архивировать

**Действие:**
```bash
# Перед удалением - сделать архив
tar -czf old_archive_$(date +%Y%m%d).tar.gz old/

# Удалить
rm -rf old/
```

#### backups_20260223/ и backups_20260223_133420/

**Расположение:** `/var/www/komunal-dom_ru/backups_20260223/`

**Содержимое:**
- Старые бэкапы БД
- Файлы анализа

**Рекомендация:** Удалить (если есть более новые бэкапы)

**Действие:**
```bash
# Удалить старые бэкапы
rm -rf backups_20260223/
rm -rf backups_20260223_133420/
```

#### doc/ и docs/

**Проблема:** Две директории документации

**Рекомендация:** Объединить в docs/

**Действие:**
```bash
# Проверить содержимое
ls -la doc/
ls -la docs/

# Переместить все в docs/
mv doc/* docs/

# Удалить пустую директорию
rmdir doc/
```

#### migrations_fixes/

**Расположение:** `/var/www/komunal-dom_ru/migrations_fixes/`

**Содержимое:**
- enhanced_aspect_bot_new_kladr.patch
- fix_building_id_8_voroshilovgradskaya.sql

**Рекомендация:** Переместить в git history или archived/

**Действие:**
```bash
# Создать archived директорию
mkdir -p archived/migrations_fixes

# Переместить
mv migrations_fixes/* archived/migrations_fixes/

# Удалить пустую директорию
rmdir migrations_fixes/
```

#### prompts_backup/

**Расположение:** `/var/www/komunal-dom_ru/prompts_backup/`

**Содержимое:** Бэкапы промптов

**Рекомендация:** Проверить, нужны ли?

**Действие:**
```bash
# Проверить содержимое
ls -la prompts_backup/

# Если не нужны - удалить
# Если нужны - переместить в archived/
```

---

## 3. ПОТЕНЦИАЛЬНЫЕ РУДИМЕНТЫ (ТРЕБУЕТ ПРОВЕРКИ)

### SemanticPattern (portal/models.py)

**Проблема:** Возможно, вытеснен CommunicativeScript

**Признаки:**
- Похожая функциональность
- Нет связей с MessageLog
- Не используется в основных flows

**Проверка:**
```sql
-- Проверить, используется ли
SELECT COUNT(*) FROM portal_semanticpattern WHERE is_active = true;
```

**Действие:**
- Если COUNT = 0 или мало - удалить
- Если используется - четко разделить с CommunicativeScript

### AIPrompt (portal/models.py)

**Проблема:** Дублирует PromptTemplate (llm_tester)

**Признаки:**
- Два хранилища промптов
- Неясно, какой использовать
- Нет связей между ними

**Проверка:**
```sql
-- Проверить, сколько промптов
SELECT COUNT(*) FROM portal_aiprompt;
SELECT COUNT(*) FROM llm_tester_prompttemplate;
```

**Действие:**
- Мигрировать AIPrompt → PromptTemplate
- Удалить AIPrompt

### ai_manager.py (portal/)

**Проблема:** Старый AI менеджер?

**Проверка:**
```bash
# Проверить использование
grep -r "ai_manager" /var/www/komunal-dom_ru/portal/
grep -r "ai_manager" /var/www/komunal-dom_ru/*.py
```

**Действие:**
- Если не используется - удалить
- Если используется - переименовать для ясности

### kladr_views.py (portal/)

**Проблема:** Почему не in kladr/?

**Проверка:**
```bash
# Проверить содержимое
head -50 /var/www/komunal-dom_ru/portal/kladr_views.py
```

**Действие:**
- Переместить в kladr/views.py
- Обновить imports

---

## 4. ЭКСПЕРИМЕНТАЛЬНЫЕ ЧАСТИ (ТРЕБУЮТ ПРОВЕРКИ)

### GigaChatService

**Файл:** `gigachat_service.py`

**Проблема:** Альтернативный LLM, используется ли?

**Проверка:**
```bash
# Проверить использование
grep -r "GigaChat" /var/www/komunal-dom_ru/
grep -r "gigachat_service" /var/www/komunal-dom_ru/
```

**Действие:**
- Если не используется - удалить
- Если используется - переместить в ai_services/

### MessageCleanerService

**Файл:** `message_cleaner_service.py`

**Проблема:** Очистка сообщений, используется ли?

**Проверка:**
```bash
# Проверить использование
grep -r "MessageCleaner" /var/www/komunal-dom_ru/
grep -r "message_cleaner_service" /var/www/komunal-dom_ru/
```

**Действие:**
- Если не используется - удалить
- Если используется - переместить в ai_services/

### CreateFilterPrompts

**Файл:** `create_filter_prompts.py`

**Проблема:** Временный скрипт?

**Проверка:**
```bash
# Проверить содержимое
head -20 /var/www/komunal-dom_ru/create_filter_prompts.py
```

**Действие:**
- Если временный - переместить в scripts/
- Если нет - переименовать для ясности

### DialogTraceService, TraceReportService

**Проблема:** Для диагностики, возможно временные

**Проверка:**
```bash
# Проверить использование
grep -r "DialogTraceService" /var/www/komunal-dom_ru/
grep -r "TraceReportService" /var/www/komunal-dom_ru/
```

**Действие:**
- Если используются для диагностики - оставить
- Если нет - переместить в tools/

---

## 5. ТЕХДОЛГ (CODE SMELLS)

### Дублирование:

1. **AIPrompt vs PromptTemplate** - два хранилища промптов
2. **SemanticPattern vs CommunicativeScript** - похожая функциональность
3. **doc/ и docs/** - две директории документации

### God Objects:

1. **portal/views.py (39KB)** - нужен рефакторинг
2. **main_agent.py** - много обязанностей

### Magic Numbers:

1. **Пороги 0.70** - hardcoded в多处
2. **TOP-10** - hardcoded
3. **Weights 0.6, 0.4** - hardcoded

### Недостаток абстракций:

1. **Нет интерфейсов** - нет абстракций для сервисов
2. **Нет IoC контейнера** - зависимости создаются напрямую
3. **Нет адаптеров** - прямые HTTP запросы к API

---

## 6. ГИПОТЕЗЫ (ТРЕБУЮТ ПРОВЕРКИ)

### Гипотеза 1: SemanticPattern не используется

**Основание:**
- Нет связей с MessageLog
- Не используется в основных flows
- CommunicativeScript вытесняет

**Проверка:**
```sql
SELECT COUNT(*) FROM portal_semanticpattern WHERE is_active = true;
```

**Действие:**
- Если COUNT = 0 или мало - удалить

### Гипотеза 2: AIPrompt дублирует PromptTemplate

**Основание:**
- Два хранилища промптов
- Неясно, какой использовать

**Проверка:**
```sql
SELECT COUNT(*) FROM portal_aiprompt;
SELECT COUNT(*) FROM llm_tester_prompttemplate;
```

**Действие:**
- Мигрировать AIPrompt → PromptTemplate
- Удалить AIPrompt

### Гипотеза 3: GigaChatService не используется

**Основание:**
- Альтернативный LLM
- Не найден в коде

**Проверка:**
```bash
grep -r "GigaChat" /var/www/komunal-dom_ru/
```

**Действие:**
- Если не используется - удалить

### Гипотеза 4: kladr_views.py должен быть in kladr/

**Основание:**
- Название указывает на КЛАДР
- Находится в portal/

**Проверка:**
```bash
head -50 /var/www/komunal-dom_ru/portal/kladr_views.py
```

**Действие:**
- Переместить в kladr/views.py

---

## 7. ПЛАН ОЧИСТКИ (PRIORITIZED)

### Приоритет 1 (Быстрые wins - 1 час):

1. **Удалить old/** - 50+ файлов
2. **Объединить doc/ и docs/** - одна директория
3. **Архивировать старые backup'ы** - оставить только 3 последних
4. **Удалить prompts_backup/** - если не используется

### Приоритет 2 (Средние - 2-4 часа):

1. **Проверить SemanticPattern** - если не используется, удалить
2. **Проверить AIPrompt** - мигрировать в PromptTemplate
3. **Проверить экспериментальные сервисы** - GigaChat, MessageCleaner
4. **Переместить kladr_views.py → kladr/views.py**

### Приоритет 3 (Сложные - 1-2 дня):

1. **Создать ai_services/** - переместить 20+ AI файлов
2. **Разбить portal/views.py** - на компоненты
3. **Унифицировать промпты** - объединить AIPrompt и PromptTemplate
4. **Добавить IoC контейнер** - для управления зависимостями

---

## 8. ЧТО НУЖНО ПРОВЕРИТЬ ВРУЧНУЮ

### SQL запросы:

```sql
-- Проверить SemanticPattern
SELECT COUNT(*) FROM portal_semanticpattern WHERE is_active = true;

-- Проверить AIPrompt
SELECT COUNT(*) FROM portal_aiprompt;

-- Проверить CommunicativeScript
SELECT script_type, COUNT(*) FROM message_handler_communicativescript
WHERE is_active = true GROUP BY script_type;

-- Проверить PromptTemplate
SELECT slug, COUNT(*) FROM llm_tester_prompttemplate
GROUP BY slug HAVING COUNT(*) > 1;

-- Проверить embedding
SELECT COUNT(*) FROM services_catalog WHERE embedding_service IS NULL;
```

### Bash команды:

```bash
# Проверить использование GigaChat
grep -r "GigaChat" /var/www/komunal-dom_ru/

# Проверить использование MessageCleaner
grep -r "MessageCleaner" /var/www/komunal-dom_ru/

# Проверить использование ai_manager
grep -r "ai_manager" /var/www/komunal-dom_ru/

# Проверить размер portal/views.py
wc -l /var/www/komunal-dom_ru/portal/views.py
```

---

## 9. МЕРЫ ПРЕДОСТОРОЖНОСТИ

### Перед удалением:

1. **Сделать backup** - всегда!
2. **Проверить git status** - что изменилось?
3. **Проверить использование** - действительно не используется?
4. **Создать issue** - задокументировать удаление

### Перед рефакторингом:

1. **Написать тесты** - если есть время
2. **Создать branch** - feature/refactor-xxx
3. **Документировать изменения** - почему refactor?
4. **Пошаговые изменения** - по одному коммиту

### Перед миграцией БД:

1. **Сделать backup БД** - pg_dump
2. **Проверить миграции** - showmigrations
3. **Протестировать на dev** - если есть dev среда
4. **Иметь rollback план** - как откатить?

---

**ВЫВОД:** Проект имеет значительный техдолг (old/, multiple backups) и architectural debt (20+ сервисов в корне, portal/views.py 39KB). Главные рудименты: old/ (50+ файлов), doc/ + docs/ (дубли), backups_20260223*/ (старые бэкапы), SemanticPattern/AIPrompt (дублирование). Quick wins: удалить old/, объединить doc/docs/, архивировать старые бэкапы, проверить использование экспериментальных сервисов.
