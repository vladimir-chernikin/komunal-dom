# SKILL: DB Entry and Schema Guard

**Назначение:** Безопасный вход в PostgreSQL через wrappers, ведение DB-справки.

**Scope:** ТОЛЬКО прямой доступ к PostgreSQL через `bin/db_*.sh`, НЕ Django runtime.

---

## АЛГОРИТМ РАБОТЫ

### ШАГ 1. ОПРЕДЕЛИТЬ INTENTION

Уточнить у пользователя, что именно нужно:

**Варианты:**
- ✅ Подключиться и проверить доступ
- ✅ Посмотреть схему/таблицы/структуру
- ✅ Выполнить SQL-запрос (SELECT/INSERT/UPDATE/DELETE)
- ✅ Изменить структуру БД (ALTER/CREATE/DROP)
- ✅ Создать пользователя или выдать права
- ❌ Django migrate (это НЕ сюда, в Django-specific skill)

**ПРОВЕРКА:**
- Если задача про Django → направить в Django workflow
- Если задача про PostgreSQL → продолжить этот Skill

---

### ШАГ 2. ИСПОЛЬЗОВАТЬ BIN/DB_*.SH WRAPPERS

**ЗАПРЕЩЕНО:** Использовать raw `psql` или `PGPASSWORD="..."`

**РАЗРЕШЕНО:** Использовать wrappers в `bin/`:

```bash
# Проверка доступа
bin/db_ping.sh

# Read-only запрос
bin/db_read.sh "SELECT * FROM services_catalog LIMIT 5;"

# Интерактивный psql
bin/db_psql.sh

# Destructive SQL
bin/db_write.sh --confirm "DROP TABLE logs;"
```

**КРИТИЧЕСКИ ВАЖНО:**
- ❌ НЕ использовать `psql` напрямую
- ❌ НЕ использовать `PGPASSWORD="..."` (никакой вариант!)
- ✅ ВСЕГДА использовать wrappers из `bin/`
- ✅ Wrappers сами загрузят credentials из `.env`

---

### ШАГ 3. ПРОВЕРИТЬ БЕЗОПАСНЫЙ ДОСТУП

**Read-only тест через wrapper:**
```bash
bin/db_ping.sh
```

**Ожидаемый результат:**
```
✅ Успешное подключение: aspect_db@aspect_objects_db
```

**ЕСЛИ ОШИБКА АУТЕНТИФИКАЦИИ:**
1. НЕ пытаться подобрать пароль
2. НЕ использовать старые значения из памяти
3. Проверить, что `.env` существует
4. Обратиться к `DB_ACCESS.md` за protocol

---

### ШАГ 4. ОПРЕДЕЛИТЬ, КАКОЙ WRAPPER ИСПОЛЬЗОВАТЬ

**Для проверки доступа:**
- Использовать `bin/db_ping.sh`

**Для read-only запросов (SELECT, \d):**
- Использовать `bin/db_read.sh "SQL_QUERY"`

**Для интерактивного psql:**
- Использовать `bin/db_psql.sh`

**Для destructive SQL (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE):**
- Использовать `bin/db_write.sh --confirm "SQL_QUERY"`
- Обязательно флаг `--confirm`!

---

### ШАГ 5. ВЫПОЛНИТЬ ЗАПРОС ЧЕРЕЗ WRAPPER

**Безопасные операции:**
```bash
bin/db_read.sh "SELECT * FROM services_catalog LIMIT 5;"
```

**Destructive операции:**
```bash
bin/db_write.sh --confirm "CREATE TABLE logs (...);"
```

**КРИТИЧЕСКИ:**
- ❌ Wrapper НЕ даст выполнить destructive SQL без `--confirm`
- ❌ `db_read.sh` запрещает destructive команды
- ✅ `db_write.sh` показывает класс риска и требует подтверждение

---

### ШАГ 6. ОТКРЫТЬ НУЖНУЮ СПРАВКУ

**Для подключения/проверки:**
- Открыть `MD_DB/DB_ACCESS.md`

**Для схемы/таблиц:**
- Открыть `MD_DB/DB_STRUCTURE.md`

**Для полного protocol:**
- Использовать этот Skill

---

### ШАГ 7. ОБНОВИТЬ DB-СПРАВКУ (ЕСЛИ СТРУКТУРА ИЗМЕНИЛАСЬ)

**КОГДА обновлять `DB_STRUCTURE.md`:**
- ✅ После создания новой таблицы
- ✅ После добавления/удаления поля
- ✅ После добавления/удаления индекса
- ✅ После изменения связи (FK)
- ✅ После переименования сущности

**ЧТО обновлять:**
- Добавить новую таблицу
- Обновить список полей
- Обновить связи
- Обновить комментарии

**КОГДА НЕ обновлять:**
- ❌ Если был просто SELECT
- ❌ Если была разовая диагностика
- ❌ Если структура не менялась

---

## ЧТО SKILL НЕ ДЕЛАЕТ

- ❌ НЕ занимается Django runtime
- ❌ НЕ подменяет собой миграционный workflow
- ❌ НЕ хранит пароль
- ❌ НЕ делает guesswork
- ❌ НЕ смешивает DB access и deploy
- ❌ НЕ выполняет raw `psql`

---

## ПРЕДОХРАНИТЕЛИ

**ЗАПРЕЩЕНО:**
- Использовать raw `psql`
- Использовать `PGPASSWORD="..."` (любой вариант!)
- Использовать пароль из памяти
- Использовать пароль из markdown
- Destructive SQL без `--confirm`
- Обновлять schema docs без подтвержденного изменения

---

## ТЕХНИЧЕСКИЙ ENFORCEMENT

**Wrappers в `bin/` обеспечивают:**
1. Автоматическую загрузку credentials из `.env`
2. Read-only тест перед сложными запросами
3. Запрет destructive operations в `db_read.sh`
4. Обязательный `--confirm` для destructive operations
5. Fail-fast если `.env` не найден

**Проверка:**
```bash
# Должно работать
bin/db_ping.sh

# Должно требовать --confirm
bin/db_write.sh "DROP TABLE test;"  # ОШИБКА: нужен --confirm

# Должно запрещать destructive
bin/db_read.sh "DROP TABLE test;"  # ОШИБКА: destructive не разрешен
```

---

## ИНТЕГРАЦИЯ С HOOK

Skill запускается из Hook: `db_access_trigger.md`

**ПАТТЕРН:**
```
User: "зайди в базу"
  ↓
Hook: Обнаружен запрос к PostgreSQL
  ↓
Hook: Направляет в этот Skill
  ↓
Skill: Использует bin/db_*.sh wrappers
```

---

## КОНТРОЛЬНЫЙ СПИСОК ПЕРЕД ВЫПОЛНЕНИЕМ

- [ ] Я использую `bin/db_*.sh`, НЕ raw psql?
- [ ] Я НЕ использую `PGPASSWORD="..."`?
- [ ] Я прочитал `DB_ACCESS.md`?
- [ ] Для destructive - есть флаг `--confirm`?
- [ ] Если структура изменилась - обновлю `DB_STRUCTURE.md`?

**ЕСЛИ ХОТЬ ОДИН "НЕТ" - ОСТАНОВИТЬСЯ!**

---

## ПРИМЕРЫ РАБОТЫ

### ПРИМЕР 1: Проверить подключение

```
User: "проверь, что БД доступна"

Skill:
1. Выполняет: bin/db_ping.sh
2. Показывает результат: ✅ Успешное подключение
3. НЕ обновляет документацию
```

### ПРИМЕР 2: Посмотреть схему

```
User: "покажи структуру services_catalog"

Skill:
1. Открывает DB_STRUCTURE.md
2. Выполняет: bin/db_read.sh "\d services_catalog"
3. Показывает результат
4. НЕ обновляет документацию
```

### ПРИМЕР 3: Destructive операция

```
User: "создай таблицу logs"

Skill:
1. Выполняет: bin/db_write.sh --confirm "CREATE TABLE logs (...);"
2. Wrapper запрашивает подтверждение
3. После подтверждения выполняет
4. ОБНОВЛЯЕТ DB_STRUCTURE.md
```

---

**ПРИНЦИП:** Skill = expert по wrappers в `bin/`, guardrail для destructive ops.
