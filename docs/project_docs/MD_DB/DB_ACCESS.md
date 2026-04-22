# DB ACCESS - Краткий справочник по доступу к PostgreSQL

**Назначение:** Краткий reference для безопасного подключения к БД.

**Полный protocol:** смотри в `.skills/db_entry_and_schema_guard.md`

---

## ИСТОЧНИК ИСТИНЫ

**ЕДИНСТВЕННЫЙ источник:** `/var/www/komunal-dom.ru/.env`

**Переменные:**
```bash
DB_NAME=aspect_objects_db
DB_USER=aspect_db
DB_PASSWORD=<смотри в .env>
DB_HOST=localhost
DB_PORT=5432
```

**Механизм:** Django использует `python-decouple` + `config()` в `settings.py`

---

## БЕЗОПАСНЫЙ ПАТТЕРН

❌ **ЗАПРЕЩЕНО:** `psql` напрямую, `PGPASSWORD="[ПАРОЛЬ БД]"`

✅ **ИСПОЛЬЗУЙТЕ** скрипты в `bin/`:

```bash
# Проверка доступа
bin/db_ping.sh

# Read-only запрос
bin/db_read.sh "SELECT * FROM services_catalog LIMIT 5;"

# Интерактивный psql
bin/db_psql.sh

# Destructive SQL (требует --confirm)
bin/db_write.sh --confirm "DROP TABLE logs;"
```

---

## ЧТО ДЕЛАТЬ ПРИ ОШИБКЕ АУТЕНТИФИКАЦИИ

1. ❌ НЕ пытаться подобрать пароль
2. ❌ НЕ использовать старые значения из памяти
3. ✅ Проверить, что `.env` существует
4. ✅ Выполнить `bin/db_ping.sh` для диагностики
5. ✅ Обратиться к `.skills/db_entry_and_schema_guard.md`

---

## ЗАПРЕЩЕННЫЕ ПАТТЕРНЫ

❌ `psql -U aspect_db -d aspect_objects_db` - raw psql
❌ `PGPASSWORD="[ПАРОЛЬ БД]"` - literal placeholder
❌ `PGPASSWORD="помнится_был_..."` - угадывание из памяти
❌ `PGPASSWORD="значение_из_документации"` - устаревшие данные

✅ `bin/db_read.sh "..."` - безопасный wrapper
✅ `bin/db_psql.sh` - безопасный интерактивный доступ

---

## СВЯЗЬ С ДРУГИМИ ФАЙЛАМИ

**Для схемы БД:** `MD_DB/DB_STRUCTURE.md`
**Для полного protocol:** `.skills/db_entry_and_schema_guard.md`
**Для Hook:** `.hooks/db_access_trigger.md`
**Для wrappers:** `bin/db_*.sh`

---

## КОНТРОЛЬНЫЙ СПИСОК

- [ ] Использую `bin/db_*.sh`, НЕ raw psql?
- [ ] НЕ перепутал пароль БД и пароль админки?
- [ ] Выполнил `bin/db_ping.sh` для проверки?

---

**ПРИНЦИП:** Reference-файл. Wrappers в `bin/` - технический enforcement.
