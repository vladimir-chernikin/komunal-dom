# КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА ДЛЯ CLAUDE

**Проект:** komunal-dom.ru (боевой Django-проект)
**Стек:** Ubuntu + Django 6.0 + gunicorn + nginx + PostgreSQL 16
**Деплой:** ручной

---

## ГЛОБАЛЬНЫЕ REUSABLE DB-ПРАВИЛА

Этот проект задаёт project-specific правила. Глобальные reusable DB-правила живут в:

- **Глобальный CLAUDE.md:** `~/.claude/CLAUDE.md`
- **Глобальный skill:** `~/.claude/skills/prod-db-access/SKILL.md`
- **Reusable wrapper:** `~/.claude/bin/komunal_dom_db.sh`

### ДОСТУП К PROD DB

Для доступа к БД этого проекта использовать **в первую очередь**:

```bash
~/.claude/bin/komunal_dom_db.sh <команда>
```

### ПРИМЕРЫ:

```bash
~/.claude/bin/komunal_dom_db.sh ping
~/.claude/bin/komunal_dom_db.sh read "SELECT current_database(), current_user;"
~/.claude/bin/komunal_dom_db.sh schema public.ai_models
~/.claude/bin/komunal_dom_db.sh table public.ai_models
```

### ЗАПРЕЩЕННЫЕ ПАТТЕРНЫ:

❌ **ЗАПРЕЩЕНО:**
- `export $(cat .env | xargs)`
- `.env | xargs`
- psql meta-команды как SQL (\d, \dt, \l, \du, \conninfo)
- Прямые вызовы `/var/www/komunal-dom_ru/bin/db_*.sh` из чата
- Печатать значения секретов

✅ **РАЗРЕШЕНО:**
- Использовать `~/.claude/bin/komunal_dom_db.sh` для всех DB операций
- Helper scripts в `/var/www/komunal-dom_ru/bin/` считать внутренним механизмом, а не интерфейсом прямого вызова из чата

### AUTOMATIC FALLBACK

При ошибках:
- Пробовать automatic fallback chain
- НЕ спрашивать "как продолжить?" если есть следующий автоматический fallback
- Для read-only задач не пытаться делать write

---

## 0. САМООБУЧЕНИЕ И ЧАСТЫЕ ОШИБКИ

**ПРАВИЛО:** После каждой ошибки НЕМЕДЛЕННО добавить инструкцию в этот раздел!

### Ошибка 1: Незаконченные имена файлов в Bash (2026-03-10)

**ОШИБКА:** `git add ai_agent_service.py filter` → syntax error

**ПРИЧИНА:** Имя файла `filter` вместо `filter_detection_service.py`

**ПРАВИЛО:**
- ✅ ВСЕГДА писать полные имена файлов
- ✅ ВСЕГДА проверять команду перед выполнением

### Ошибка 2: Забыл сделать коммит после изменений (2026-03-10)

**ОШИБКА:** Выполнил задачи, но забыл закоммитить

**ПРИЧИНА:** Сосредоточился на выполнении задач, забыл про Git workflow

**ПРАВИЛО:**
- ✅ После завершения ЛОГИЧЕСКИ ЗАВЕРШЕННОГО шага: `git status`
- ✅ Если есть изменения → `git add` + `git commit`
- ✅ НЕ переходить к следующей задаче БЕЗ коммита

**УТОЧНЕНИЕ:** Коммитить после атомарного, логически завершенного изменения (исправил баг, добавил функцию), НЕ после каждого микро-движения.

### Ошибка 3: Забыл перезапустить Gunicorn (2026-03-10)

**ОШИБКА:** Изменил .py файл, но изменения не применяются

**ПРИЧИНА:** Gunicorn workers кешируют Python код в памяти при загрузке

**ПРАВИЛО:**
- ✅ После изменений .py файлов, которые используются Django: `systemctl restart gunicorn-komunal-dom`
- ✅ Проверить статус: `systemctl status gunicorn-komunal-dom`
- ❌ ЗАПРЕЩЕНО: Изменять код БЕЗ последующего перезапуска gunicorn

**УТОЧНЕНИЕ ПО ТЕМПЛАТАМ:**
- Django templates кешируются в памяти при первом использовании
- Если изменил .html шаблон → нужно перезагрузить gunicorn ИЛИ дождаться пересборки кэша
- В production безопаснее ВСЕГДА перезапускать после изменений .py ИЛИ .html

### Ошибка 4: Забыл установить права на файлы (2026-03-10)

**ОШИБКА:** Создал файлы через Write tool, но nginx/gunicorn не может их читать

**ПРИЧИНА:** Файлы создаются от root с правами 600, а nginx работает от www-data

**ПРАВИЛО:**
- ✅ СРАЗУ после Write tool: `chmod 644 файл` && `chown olga:www-data файл`
- ❌ ЗАПРЕЩЕНО: Создавать файлы БЕЗ установки прав

### Ошибка 5: Использовал неправильный пароль БД (2026-03-10)

**ОШИБКА:** `password authentication failed for user "aspect_db"`

**ПРИЧИНА:** Перепутал или неправильно использовал пароли:
- ❌ Пароль Django суперпользователя ≠ пароль PostgreSQL
- ❌ Placeholder `[ПАРОЛЬ БД]` использовался как literal value
- ❌ Пароль брался из памяти/документации вместо `.env`

**ПРАВИЛО:**
- ✅ PostgreSQL доступ: использовать `bin/db_*.sh` скрипты
- ✅ Скрипты сами загрузят credentials из `.env`
- ✅ Django админка: пароль в таблице `auth_user`
- ❌ ЗАПРЕЩЕНО: Использовать `PGPASSWORD="[ПАРОЛЬ БД]"` как команду
- ❌ ЗАПРЕЩЕНО: Использовать raw `psql` напрямую
- ⚠️ **КРИТИЧНО:** Пароли только в `.env`, НЕ в документации!

### Ошибка 6: Пытался создать пользователя PostgreSQL от имени aspect_db (2026-03-10)

**ОШИБКА:** `CREATE USER aspect_alex` от имени aspect_db → permission denied

**ПРИЧИНА:** У aspect_db нет права CREATEROLE

**ПРАВИЛО:**
- ✅ Создание пользователей: `sudo -u postgres psql -c "CREATE USER ..."`
- ❌ ЗАПРЕЩЕНО: Создавать пользователей от обычных пользователей БД

### Ошибка 7: Git коммиты от разных пользователей (2026-03-10)

**ОШИБКА:** Коммиты от root помечены как "Olga"

**ПРИЧИНА:** Локальная конфигурация в `.git/config`

**ПРАВИЛО:**
- ✅ Удалить локальную конфигурацию: `git config --local --unset user.name`
- ❌ ЗАПРЕЩЕНО: Коммитить с чужим именем!

### Ошибка 8: setfacl command not found (2026-03-10)

**ОШИБКА:** Команда не найдена

**ПРИЧИНА:** Пакет acl не установлен в системе

**ПРАВИЛО:**
- ✅ Если команда не найдена: `sudo apt install пакет`
- ❌ ЗАПРЕЩЕНО: Использовать команды без проверки их наличия

### Ошибка 9: Создавал объекты в БД без обязательных полей (2026-03-10)

**ОШИБКА:** `UserProfile.objects.create(...)` → null value in column "timezone"

**ПРИЧИНА:** Поле `timezone` есть в БД (NOT NULL), но не было в модели Django

**ПРАВИЛО:**
- ✅ ВСЕГДА проверять структуру таблицы: `\d table_name`
- ✅ Синхронизировать модель Django с БД
- ✅ При создании объектов указывать ВСЕ NOT NULL поля
- ❌ ЗАПРЕЩЕНО: Создавать объекты без обязательных полей

### Ошибка 10: Использовал setfacl, но можно обойтись chmod + группы (2026-03-10)

**ОШИБКА:** Сразу пытался использовать setfacl, хотя хватило бы chmod

**ПРИЧИНА:** Не проверил более простые решения

**ПРАВИЛО:**
- ✅ СНАЧАЛА попробовать простое решение: chmod + группы
- ✅ Использовать setfacl ТОЛЬКО для сложных ACL
- ❌ ЗАПРЕЩЕНО: Усложнять там, где достаточно простого решения

### Ошибка 11: Локальный импорт mark_safe в методах admin (2026-03-22)

**ОШИБКА:** `NameError: name 'mark_safe' is not defined` в admin.py

**ПРИЧИНА:** Использовал `mark_safe` в нескольких методах admin, но импортировал его локально внутри каждого метода. В одном методе забыл добавить импорт.

**НЕПРАВИЛЬНО:**
```python
def method1(self, obj):
    from django.utils.safestring import mark_safe  # локальный импорт
    return mark_safe(...)

def method2(self, obj):
    return mark_safe(...)  # ОШИБКА: mark_safe не импортирован!
```

**ПРАВИЛО:**
- ✅ Если используешь `mark_safe` в НЕСКОЛЬКИХ методах admin → импортируй ОДИН РАЗ в начале файла
- ✅ Правильный импорт: `from django.utils.safestring import mark_safe` (в начале файла)
- ❌ ЗАПРЕЩЕНО: Локальные импорты `from django.utils.safestring import mark_safe` внутри методов
- ✅ ПРОВЕРКА перед использованием mark_safe: есть ли импорт в начале файла?

### Ошибка 12: Использовал placeholder/устаревшее значение вместо реального DB source of truth (2026-03-22)

**ОШИБКА:** `password authentication failed for user "aspect_db"` или `FATAL: password authentication failed`

**ПРИЧИНА:**
- Использовал placeholder `[ПАРОЛЬ БД]` как literal строку вместо реального значения
- Брал пароль из памяти/старой документации вместо актуального `.env`
- Перепутал пароль Django-админки и пароль PostgreSQL
- Использовал устаревший `.env` или не тот файл конфигурации

**ПРАВИЛО:**
- ✅ **ЕДИНСТВЕННЫЙ источник истины** - файл `.env` в корне проекта
- ✅ **СНАЧАЛА** прочитать `MD_DB/DB_ACCESS.md` перед любым SQL/psql
- ✅ Использовать глобальный wrapper: `~/.claude/bin/komunal_dom_db.sh`
- ✅ Использовать `$DB_PASSWORD` вместо literal values
- ✅ Проверить соединение тестом перед сложными запросами
- ❌ **ЗАПРЕЩЕНО:** Угадывать пароль из памяти или старых сессий
- ❌ **ЗАПРЕЩЕНО:** Использовать placeholder `[ПАРОЛЬ БД]` как реальное значение
- ❌ **ЗАПРЕЩЕНО:** Брать пароль из документации (MD_DB, markdown)
- ❌ **ЗАПРЕЩЕНО:** Подставлять literal password в команды
- ❌ **ЗАПРЕЩЕНО:** Использовать `export $(cat .env | grep -v '^#' | xargs)`
- ⚠️ **КРИТИЧНО:** Пароль PostgreSQL (`.env` → `DB_PASSWORD`) ≠ пароль Django-админки

**ПРАВИЛЬНЫЙ ПАТТЕРН:**
```bash
# 1. Использовать глобальный wrapper (автоматически загрузит credentials из .env)
~/.claude/bin/komunal_dom_db.sh ping
~/.claude/bin/komunal_dom_db.sh read "SELECT current_database(), current_user;"

# 2. Для сложных запросов
~/.claude/bin/komunal_dom_db.sh read "SELECT * FROM ai_models WHERE is_active = true;"
```

**ПРОВЕРКА ПЕРЕД SQL:**
- [ ] Я прочитал `MD_DB/DB_ACCESS.md`?
- [ ] Я использую `~/.claude/bin/komunal_dom_db.sh`?
- [ ] Я НЕ перепутал пароль БД и пароль админки?
- [ ] Я выполнил тест соединения через wrapper?

**ЕСЛИ ХОТЬ ОДИН ОТВЕТ "НЕТ" - ОСТАНОВИТЬСЯ!**

### Ошибка 13: Bash auto-denied в режиме dontAsk на типовых Django-командах (2026-04-09)

**ОШИБКА:** `Permission to use Bash has been auto-denied in dontAsk mode`

**ПРИЧИНА:**
- Команда была сформирована в нетипичном виде и не попала под allowlist
- Использовался `source .../venv/bin/activate && python manage.py ...`, хотя можно было вызвать `venv/bin/python manage.py ...` напрямую
- После auto-denied не был сделан немедленный retry эквивалентной разрешенной командой

**ПРАВИЛО:**
- ✅ Для Django-команд ПРЕДПОЧИТАТЬ прямой вызов:
  - `venv/bin/python manage.py <команда>`
  - `/var/www/komunal-dom_ru/venv/bin/python manage.py <команда>`
- ✅ `source .../activate` использовать только если прямой вызов реально не подходит
- ✅ Если Bash auto-denied в `dontAsk`, СРАЗУ повторить задачу эквивалентной разрешенной командой, а не останавливаться
- ✅ Для `check`, `migrate`, `shell`, `showmigrations`, `makemigrations` использовать короткие прямые команды без лишней shell-обвязки
- ❌ ЗАПРЕЩЕНО: завершать задачу из-за одного auto-denied, если есть эквивалентная разрешенная команда

### Ошибка 14: Error editing file / сбой редактирования файла (2026-04-09)

**ОШИБКА:** `Error editing file`

**ПРИЧИНА:**
- Несколько подряд правок по одному и тому же файлу без повторного чтения
- Сложный многофрагментный edit в файле с нестандартной кодировкой, BOM или CRLF
- Попытка продолжать тем же способом после первой ошибки редактирования

**ПРАВИЛО:**
- ✅ Если `Edit` или `MultiEdit` на файле упал хотя бы ОДИН РАЗ:
  1. заново перечитать текущий файл целиком
  2. НЕ повторять тот же сбойный edit-паттерн
  3. перейти на более надежный способ:
     - один цельный `Write`
     - или безопасная перезапись файла через временный файл и замену
- ✅ Перед правкой shell/json/yaml/md/python-файлов с подозрением на CRLF/BOM сначала нормализовать формат
- ✅ После перезаписи файла сразу проверить:
  - файл читается
  - синтаксис не сломан
  - права на файл корректны
- ✅ После создания или полной замены файла: `chmod 644 файл && chown olga:www-data файл`
- ❌ ЗАПРЕЩЕНО: делать 3-4 повторных `Edit` подряд в тот же файл после первой ошибки
- ❌ ЗАПРЕЩЕНО: считать ошибку редактирования причиной остановки, если файл можно надежно переписать целиком

---

## 1. ЯЗЫК ОБЩЕНИЯ - ТОЛЬКО РУССКИЙ

**КРИТИЧЕСКИ ВАЖНО:** ВСЯ коммуникация - ИСКЛЮЧИТЕЛЬНО на русском!

- ❌ ЗАПРЕЩЕНО: Писать на английском
- ✅ ОБЯЗАТЕЛЬНО: Все ответы, объяснения, комментарии на русском
- ✅ Технические термины - транслитом или с русским объяснением

**ПРОВЕРКА:** Я пишу на русском? Если нет - ПЕРЕПИСАТЬ!

---

## 2. ПРОТОКОЛ РАБОТЫ "СНАЧАЛА ФАКТЫ, ПОТОМ ПРАВКА"

**КРИТИЧЕСКИ ВАЖНО:** Никаких действий без сбора фактов!

### Обязательный порядок:

1. **СБОР ФАКТОВ:**
   - Прочитать соответствующие файлы
   - Проверить текущее состояние (`git status`, `systemctl status`)
   - Изучить логи/ошибки
   - Понять контекст

2. **ДИАГНОСТИКА:**
   - В чем проблема?
   - Какие есть варианты решения?
   - Какой вариант наименее рискован?

3. **ПЛАН:**
   - Короткий план действий
   - Проверка рисков

4. **ПРАВКА:**
   - Внести изменения
   - Проверить результат

**ПРОВЕРКА:** Я собрал факты? Если нет - НЕ ДЕЛАТЬ ИЗМЕНЕНИЙ!

---

## 3. КОГДА ЧИТАТЬ MD_DB

**КРИТИЧЕСКИ ВАЖНО:** MD_DB - это база знаний проекта, НЕ читать ее автоматически каждую задачу!

### КОГДА НЕ ЧИТАТЬ MD_DB:

- ✅ Обычная правка кода без доменной неопределенности
- ✅ Изменения в views.py, urls.py, forms.py
- ✅ Добавление простых функций/методов
- ✅ Рефакторинг кода без изменения архитектуры

### КОГДА ЧИТАТЬ ОДИН ПРОФИЛЬНЫЙ ФАЙЛ:

| Тип задачи | Файл MD_DB |
|---|---|
| **Вопросы по DB access / psql / credentials / connection** | `DB_ACCESS.md` |
| Вопросы по схеме БД, таблицам, связям | `DB_STRUCTURE.md` |
| Вопросы по AI-архитектуре, поиску | `AI_ARCHITECTURE.md` |
| Вопросы по runtime, deploy, командам | `DEPLOY_RUNTIME.md` |
| Вопросы по трассировке, диагностике | `DIAGNOSTICS.md` |
| Поиск конкретного файла или сервиса | `PROJECT_STRUCTURE.md` |

### КОГДА ЧИТАТЬ INDEX.md:

- ✅ Первый раз в проекте
- ✅ Непонятна структура проекта
- ✅ Нужно понять, какие файлы есть в MD_DB
- ✅ Поиск нужного раздела

### КОГДА ЧИТАТЬ НЕСКОЛЬКО ФАЙЛОВ:

- ✅ Сложная архитектурная задача (затрагивает БД + AI + deploy)
- ✅ Диагностика неизвестной проблемы
- ✅ Ревью проекта

**ПРАВИЛО:** СНАЧАЛА понять тип задачи, ПОТОМ выбрать нужный файл(ы) из MD_DB, НЕ читать весь MD_DB целиком!

---

## 4. GIT-ДИСЦИПЛИНА

### Основные правила:

**ПРАВИЛО:** ВСЯ работа в feature-ветках, НИКОГДА не напрямую в main!

1. ❌ **ЗАПРЕЩЕНО:** Работать в `main`
2. ✅ **ВСЕГДА:** Создавать branch под каждую задачу
3. ✅ **ЧАСТО:** Коммитить после логически завершенного шага
4. ✅ **ЯСНО:** Писать понятные сообщения коммитов

### Обязательный workflow:

```bash
# 1. Проверить статус (ПЕРЕД ЛЮБЫМИ ДЕЙСТВИЯМИ)
git status --short

# 2. Создать ветку (ОДИН РАЗ)
git checkout main
git pull origin main
git checkout -b feature/краткое-описание

# 3. Работаем, коммитим после завершенных шагов
git add конкретный_файл.py  # НЕ git add .
git commit -m "Описание завершенного шага"
git push

# ... работаем дальше ...
git add другой_файл.py
git commit -m "Еще один завершенный шаг"
git push

# 4. После завершения ВСЕЙ задачи - PR
gh pr create --title "Название" --body "Описание..."
```

### Обязательные проверки:

**ПЕРЕД коммитом:**
```bash
git status --short      # Что изменилось?
git diff                # Что именно в файлах?
git diff --staged       # Что попадет в коммит?
```

**ПРОВЕРКА ПЕРЕД КАЖДЫМ ИЗМЕНЕНИЕМ:**
- Я в какой ветке? (`git branch`)
- Я сделал `git status`?
- Я закоммичу СРАЗУ после завершения шага?
- Я создам PR только после завершения ВСЕЙ задачи?

### КОГДА ДЕЛАТЬ КОММИТ:

✅ **После ЛОГИЧЕСКИ ЗАВЕРШЕННОГО шага:**
- Исправил баг → коммит
- Добавил небольшую функцию → коммит
- Завершил рефакторинг модуля → коммит
- **ЗАВЕРШИЛ ЗАДАЧУ** → НЕМЕДЛЕННО коммит!

❌ **ЗАПРЕЩЕНО:**
- Оставлять изменения незакоммиченными "на потом"
- Делать несколько изменений перед коммитом
- **Переходить к следующей задаче БЕЗ коммита!**

**УТОЧНЕНИЕ:** Коммитить после атомарного, логически завершенного изменения. НЕ после каждого микро-движения, но и НЕ копить изменения на долго.

---

## 5. RUNTIME-ДИСЦИПЛИНА

### Django операции:

**КОГДА НУЖЕН migrate:**
- ✅ После изменений models.py
- ✅ После добавления новых Django приложений
- ❌ НЕ нужен после изменений views.py, urls.py, templates

**КОГДА НУЖЕН collectstatic:**
- ✅ После добавления/изменения статических файлов
- ✅ После изменения STATIC settings
- ❌ НЕ нужен после изменений .py файлов (кроме settings)

### gunicorn restart:

**НУЖЕН RESTART:**
- ✅ После изменений .py файлов (views, models, services)
- ✅ После изменений настроек Django
- ✅ После добавления новых Django приложений
- ✅ После изменений .html шаблонов (для надежности в production)

**НЕ НУЖЕН RESTART:**
- ❌ Изменения статических файлов (.css, .js) - nginx отдает напрямую

**ОБЯЗАТЕЛЬНЫЙ ЧЕК-ЛИСТ ПОСЛЕ ИЗМЕНЕНИЙ .py ФАЙЛОВ:**
```bash
# 1. Изменить .py файл

# 2. Перезапустить gunicorn
systemctl restart gunicorn-komunal-dom

# 3. Проверить статус
systemctl status gunicorn-komunal-dom --no-pager -l | head -15

# 4. Проверить что запустился НОВЫЙ процесс (Active: active (running) since СЕЙЧАС)
```

**ВАЖНО:** Gunicorn workers кешируют код при загрузке! Без restart они будут использовать СТАРЫЙ код!

### nginx reload/restart:

**КОГДА НУЖЕН reload:**
- ✅ После изменений nginx конфигурации
- ✅ Без разрыва соединений

**КОГДА НУЖЕН restart:**
- ✅ После серьезных изменений конфигурации
- ✅ С разрывом соединений

**ПРОВЕРКА:**
```bash
nginx -t                    # Проверка конфигурации
systemctl reload nginx      # Перезагрузка
systemctl status nginx      # Проверка статуса
```

**ЗАПРЕЩЕНО:** restart как первое действие без диагностики!

### Очистка кэша Python:

**КОГДА НУЖНА:**
- ⚠️ После изменений структуры пакетов (удаление/добавление модулей)
- ⚠️ После странных ошибок импорта
- ❌ НЕ нужна после обычных изменений кода

**КОМАНДА:**
```bash
find /var/www/komunal-dom_ru/__pycache__ -name "*.pyc" -delete
```

**ПРОВЕРКА:** Если есть сомнения - можно почистить, НО это НЕ обязателный шаг.

---

## 6. ЗАПРЕТЫ И ПРАВИЛА

### ЗАПРЕТ НА ЭМОДЗИ

**КРИТИЧЕСКИ ВАЖНО:** В проекте komunal-dom.ru категорически запрещено использовать эмодзи в коде, текстах бота и интерфейсах.

### СТИЛЬ ОБЩЕНИЯ

**Прямой, деловой, по делу. Избегайте избыточных рассуждений и вежливостей.**

### ПРАВИЛА РАБОТЫ С ДАННЫМИ

**КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО редактировать данные в БД без разрешения:**

❌ **ЗАПРЕЩЕНЫ:**
- Добавление тегов, изменение услуг, модификация данных
- INSERT/UPDATE запросы к services_catalog и другим таблицам

✅ **РАЗРЕШЕНЫ:**
- Чтение данных (SELECT)
- Изменение кода и конфигурационных файлов

**ОБЯЗАТЕЛЬНАЯ ПРОЦЕДУРА:**
1. Попросить разрешение
2. Описать изменения
3. Получить подтверждение
4. Вносить изменения

### ЗАПРЕТ НА HARDCODE ДАННЫХ И КЛАССИФИКАЦИИ

**КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:**
- ❌ Хардкод списков keywords, правил классификации
- ❌ Вложенные if/else цепочки для классификации текста

**ПРАВИЛЬНЫЙ ПОДХОД:**
- ✅ Использовать LLM (AIAgentService, FilterDetectionService)
- ✅ Хранить данные в БД
- ✅ Использовать векторный поиск (VectorSearchService)
- ✅ Использовать теговый поиск (TagSearchService)

**ИСКЛЮЧЕНИЯ:** Технические константы, stopwords для NLP, временные заглушки с `# TODO: заменить на LLM/БД`

### ПРАВА ДОСТУПА

**После создания файлов через Write tool:**
```bash
# ОБЯЗАТЕЛЬНО для Django шаблонов
chmod 644 файл.html
chown olga:www-data файл.html

# ОБЯЗАТЕЛЬНО для файлов в /tmp
chmod 644 /tmp/файл
```

**ПРОВЕРКА:**
```bash
ls -la файл                    # Проверить владельца и права
```

### ОБЯЗАТЕЛЬНОЕ ТЕСТИРОВАНИЕ

**После изменений файлов, используемых Django:**

1. **Права доступа:**
   ```bash
   chmod 644 файл.html
   chown olga:www-data файл.html
   ```

2. **Перезапуск gunicorn:**
   ```bash
   systemctl restart gunicorn-komunal-dom
   systemctl status gunicorn-komunal-dom
   ```

3. **Проверка доступности:**
   ```bash
   curl -I http://localhost:8000/путь/к/странице/
   ```

**ПРОВЕРКА ПЕРЕД ЗАВЕРШЕНИЕМ:**
- Я установил права?
- Я перезапустил gunicorn?
- Я проверил доступность?

---

## 7. КОГДА ОБНОВЛЯТЬ MD_DB

**КРИТИЧЕСКИ ВАЖНО:** MD_DB - это база знаний, НЕ писать туда временные заметки!

### КОГДА ДОПИСЫВАТЬ В MD_DB:

✅ **Стабильное проектное знание:**
- Факты об архитектуре (схемы, потоки данных)
- Справочные данные (структура БД, команды)
- Диагностические сценарии (которые пригодятся повторно)
-Runtime-факты (команды, конфигурации)

❌ **НЕ писать в MD_DB:**
- Одноразовые заметки по конкретной задаче
- Временные гипотезы без пометки "ГИПОТЕЗА"
- Сырые логи целиком
- Task-specific мусор
- Operational правила (это в CLAUDE.md)

### ЧТО ПИСАТЬ В CLAUDE.md:

✅ **Правила поведения и дисциплина:**
- Приказы (что делать, что НЕ делать)
- Протоколы работы ("сначала факты, потом правка")
- Git-дисциплина
- Runtime-дисциплина
- Правила безопасности
- Правила обращения к MD_DB

### ЧТО ПИСАТЬ В SKILLS (кандидаты):

✅ **Повторяемые узкие процедуры:**
- DB Access (подключение к PostgreSQL, проверки credentials, безопасные паттерны) - см. `DB_ACCESS.md`
- DB Operations (SQL запросы, миграции, создание пользователей)
- Diagnostics (трассировка, генерация отчетов)
- Deploy/Runtime (systemctl команды, nginx reload/restart)

**КРИТЕРИЙ:** Если процедура повторяется 3+ раз и имеет четкие шаги → кандидат на Skill.

### ДОПОЛНИТЕЛЬНО ПРИ ОБНОВЛЕНИИ MD_DB:

✅ **Обновлять `DB_ACCESS.md` когда:**
- Изменился механизм загрузки credentials (другой файл, другой способ)
- Добавился новый источник конфигурации (systemd env, переменные окружения)
- Изменились runtime-паттерны подключения к БД
- Обнаружена новая типичная ошибка аутентификации

❌ **НЕ писать в `DB_ACCESS.md`:**
- Реальные пароли и секреты (только mechanism, not secret value)
- Структуру таблиц БД (это в `DB_STRUCTURE.md`)
- Одноразовые SQL запросы для конкретной задачи

---

## 8. БАЗА ЗНАНИЙ (MD_DB)

**Полная документация вынесена в папку `MD_DB/`**

### Быстрые ссылки:

**[MD_DB/INDEX.md](MD_DB/INDEX.md)** - Начните с этого файла! (роутер по базе знаний)

**[MD_DB/DB_STRUCTURE.md](MD_DB/DB_STRUCTURE.md)** - Справочник по БД
- Открывать: когда вопросы по БД, схеме, таблицам, ролям
- Обновлять: при изменении структуры БД

**[MD_DB/AI_ARCHITECTURE.md](MD_DB/AI_ARCHITECTURE.md)** - AI-архитектура
- Открывать: когда вопросы по AI, поиску, микросервисам
- Обновлять: при изменении AI-архитектуры

**[MD_DB/DEPLOY_RUNTIME.md](MD_DB/DEPLOY_RUNTIME.md)** - Развертывание и runtime
- Открывать: когда вопросы по deploy, runtime, командам
- Обновлять: при изменении runtime-конфигурации

**[MD_DB/DIAGNOSTICS.md](MD_DB/DIAGNOSTICS.md)** - Диагностика
- Открывать: когда нужна трассировка, диагностика проблем
- Обновлять: при добавлении новых диагностических инструментов

---

## 9. HOOKS И SKILLS

**Структура:**
- `.hooks/` - Hook файлы (триггеры и маршрутизаторы)
- `.skills/` - Skill файлы (исполнители и эксперты)

**ПРИНЦИП:** Hook = триггер и маршрутизатор, Skill = исполнитель и эксперт.

---

### АКТИВНЫЕ HOOKS И SKILLS

#### `.hooks/db_access_trigger.md` + `.skills/db_entry_and_schema_guard.md`

**Назначение:** Безопасный вход в PostgreSQL и ведение DB-справки.

**КОГДА используется:**
- ✅ Прямой доступ к PostgreSQL (psql, SQL команды)
- ✅ Проверка подключения к БД
- ✅ Просмотр схемы/таблиц
- ✅ Выполнение SQL запросов
- ✅ Изменение структуры БД (ALTER/CREATE/DROP)

**КОГДА НЕ используется:**
- ❌ Django задачи (migrate, collectstatic)
- ❌ Runtime операции (gunicorn, nginx)
- ❌ Обсуждение БД без прямого доступа

**ЧТО делает:**
1. **Hook** перехватывает попытку прямого DB access
2. **Skill** безопасно загружает credentials из `.env`
3. **Skill** выполняет read-only тест соединения
4. **Skill** открывает нужную справку (`DB_ACCESS.md` или `DB_STRUCTURE.md`)
5. **Skill** выполняет SQL запрос (если требуется)
6. **Skill** обновляет `DB_STRUCTURE.md` (если структура изменилась)

**КРИТИЧЕСКИЕ ПРАВИЛА:**
- ✅ **ВСЕГДА** идти через этот Skill для прямого DB access
- ✅ **НИКОГДА** не использовать psql напрямую
- ✅ **ВСЕГДА** загружать credentials из `.env`
- ✅ **ВСЕГДА** обновлять `DB_STRUCTURE.md` после изменения структуры
- ❌ **НЕ** использовать пароль из памяти/документации
- ❌ **НЕ** выполнять destructive SQL без подтверждения

---

#### Figma + Django UI Workflow

**Официальный skill:** `.claude/skills/figma-django-ui-workflow/SKILL.md`

**Назначение:** Анализ и перестройка Django UI по form contract и Figma дизайну.

**КОГДА используется:**
- ✅ Изменение Django templates (.html)
- ✅ Изменение views, forms, admin для UI
- ✅ Перестройка экранов по Figma design
- ✅ Синхронизация UI с form contract

**КОГДА НЕ используется:**
- ❌ Изменение models.py (это DB schema, не UI)
- ❌ Изменение business logic без UI impact

**Стандартный режим:** Анализ → Contract → Figma → Diff-plan → Изменения (после подтверждения)

**WorkOrder специфика:**
- Contract: `tmp_archive/work_order_contract_v0.2_normalized.yaml`
- Профили: detail_operator, detail_full, create
- Template: `work_orders/templates/work_orders/work_order_detail.html`

---

### UI TOOLCHAIN

Use this toolchain in this project:
- Plugin: komunal-dom-ui-ops
- Plugin: frontend-design
- Plugin: hookify
- Plugin: figma
- MCP: playwright

Config locations:
- .claude-plugin/marketplace.json
- .mcp.json
- .claude/hookify.*.local.md
- bin/claude-project.sh

Rules:
- For form and layout tasks, use playwright and save screenshots under tmp_archive/ui_runs/<run_id>/
- For form tasks, do not stop at diff-plan; carry through patch -> restart/reload -> browser verification -> screenshots
- For field moves between tables, use schema-lift-fields first and inspect models, migrations, RunSQL, raw SQL, admin, and templates
- Use frontend-design for layout and visual composition improvements
- Use hookify as a reminder layer, not as the only protection for prod DB or dangerous shell commands

---

### КАК ДОБАВЛЯТЬ НОВЫЕ HOOKS/SKILLS

**Когда создавать Hook:**
- Повторяющийся паттерн задач (3+ раз)
- Нужен перехват определенных попыток действий
- Нужна маршрутизация в конкретный Skill

**Когда создавать Skill:**
- Узкая процедура с четкими шагами
- Нужен экспертный knowledge в конкретной области
- Нужны guardrails и предохранители

**НЕ превращать в Hooks/Skills:**
- Одноразовые задачи
- Большие монолитные процедуры
- Задачи без повторяемости

---

## 10. КРИТИЧЕСКАЯ ПРОВЕРКА ПЕРЕД ЛЮБЫМ ДЕЙСТВИЕМ

**СПИСОК ПРОВЕРКИ:**

- [ ] Я собрал факты? (прочитал файлы, проверил статус)
- [ ] Я в правильной ветке? (`git branch`)
- [ ] Я сделал `git status --short`?
- [ ] Я понимаю, что делаю?
- [ ] Я знаю, как проверить результат?
- [ ] Я закоммичу после завершения шага?
- [ ] Я перезапущу gunicorn после .py изменений?
- [ ] Я установлю права на новые файлы?

**ЕСЛИ ХОТЬ ОДИН ОТВЕТ "НЕТ" - ОСТАНОВИТЬСЯ!**


### MIGRATION AND UI GUARDRAILS

Before schema migrations:
- verify real schemas/tables via information_schema or Django introspection
- do not assume public vs request_mgmt from model names alone
- do not report success if admin form construction raises FieldError or if browser artifacts are missing

Before manage.py usage:
- do not pass --skip-checks to `python manage.py check`
- use app-specific migrate only after verifying migration dependencies

For User admin changes:
- if fields live on UserProfile, do not place them directly into BaseUserAdmin fieldsets as native User fields without a custom form layer

For browser verification:
- use project MCP server `playwright`
- save screenshots and report.json under tmp_archive/ui_runs/<run_id>/

### ADMIN SELF-CHECK

After any changes to `portal/admin.py`, `templates/admin/`, `forms.py`, `models.py`, or `migrations/`:
- run a page-level smoke check before reporting success
- open the changed admin form in a browser or run `bin/run_admin_ui_smoke.sh <run_id>`
- if the page shows `FieldError`, `Traceback`, `Server Error (500)`, or missing expected controls, do not stop
- if a dependent form control is part of the task, verify the real browser behavior after changing the parent field
- if a parent-child pair like `company -> department` still allows invalid combinations in the browser, treat that as a failed task even if server-side validation exists
- treat that result as an unfinished task and immediately start the next fix cycle
- only report success after the smoke check exits with code 0 and screenshots/report.json are saved
