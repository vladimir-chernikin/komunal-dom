# HOOK: DB Access Trigger

**Назначение:** Перехватывать попытки прямого доступа к PostgreSQL и перенаправлять в Skill.

**Приоритет:** Критический (срабатывает перед выполнением любой DB-операции)

---

## КОГДА СРАБАТЫВАЕТ

Hook срабатывает при обнаружении любых из этих паттернов:

### Прямые команды psql:
- `psql`
- `\d`, `\dt`, `\dv`, `\di`, `\l`
- `\connect`, `\c`

### SQL-команды:
- `SELECT`, `INSERT`, `UPDATE`, `DELETE`
- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`
- `CREATE INDEX`, `DROP INDEX`
- `TRUNCATE`, `GRANT`, `REVOKE`
- `CREATE USER`, `DROP USER`

### Явные запросы пользователя:
- "зайди в базу"
- "сделай SQL-запрос"
- "посмотри таблицу в postgres"
- "проверь схему БД"
- "подключись к PostgreSQL"
- "выполни запрос к БД"
- "покажи данные из таблицы"

### Диагностические запросы:
- "проверь подключение к БД"
- "есть ли доступ к postgres"
- "проверь пользователя aspect_db"

---

## КОГДА НЕ СРАБАТЫВАЕТ

- ❌ Django-задачи (`migrate`, `collectstatic`, `createsuperuser`)
- ❌ Runtime операции (`gunicorn restart`, `nginx reload`)
- ❌ Чтение models.py без намерения подключаться
- ❌ Обсуждение структуры БД без прямого доступа
- ❌ Изменение Python кода проекта
- ❌ Работа с git, файлами, директориями

---

## ЧТО ДЕЛАЕТ HOOK

1. **Останавливает** попытку использовать raw `psql` или `PGPASSWORD="..."`
2. **Направляет** в Skill `db_entry_and_schema_guard`
3. **НЕ выполняет** саму бизнес-логику доступа
4. **НЕ хранит** секреты

---

## ПРЕДОХРАНИТЕЛИ

Hook блокирует выполнение если:

- Попытка использовать `psql` напрямую
- Попытка использовать `PGPASSWORD="..."` (любой вариант)
- Попытка использовать пароль из памяти/документации
- Destructive SQL без подтверждения

---

## ТЕХНИЧЕСКИЙ ENFORCEMENT

**КРИТИЧЕСКОЕ ПРАВИЛО:** PostgreSQL доступ ТОЛЬКО через `bin/db_*.sh` wrappers.

❌ **ЗАПРЕЩЕНО:**
```bash
psql -U aspect_db -d aspect_objects_db
PGPASSWORD="..." psql ...
```

✅ **РАЗРЕШЕНО:**
```bash
bin/db_ping.sh          # Проверка доступа
bin/db_read.sh "..."    # Read-only запросы
bin/db_psql.sh          # Интерактивный psql
bin/db_write.sh --confirm "..."  # Destructive SQL
```

---

## ИНТЕГРАЦИЯ С SKILL

Hook всегда запускает Skill: `db_entry_and_schema_guard`

**ПАТТЕРН:**
```
User: "зайди в базу данных"
  ↓
Hook: Срабатывает (обнаружен запрос к PostgreSQL)
  ↓
Hook: Направляет в Skill db_entry_and_schema_guard
  ↓
Skill: Использует bin/db_*.sh wrappers
```

---

## КРИТИЧЕСКИЕ ПРАВИЛА

1. ✅ **ВСЕГДА** перенаправлять в Skill при обнаружении DB-операций
2. ✅ **НИКОГДА** не выполнять `psql` напрямую
3. ✅ **ВСЕГДА** использовать `bin/db_*.sh` wrappers
4. ✅ **ВСЕГДА** проверять destructive операции
5. ❌ **НЕ ХРАНИТЬ** пароли в Hook
6. ❌ **НЕ ДЕЛАТЬ** guesswork про credentials

---

**ПРИНЦИП:** Hook = триггер и маршрутизатор к wrappers в `bin/`.
