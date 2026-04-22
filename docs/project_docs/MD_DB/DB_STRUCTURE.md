# СТРУКТУРА БАЗЫ ДАННЫХ

## Общая информация

**База данных:** PostgreSQL 16
**Имя БД:** `aspect_objects_db`
**Пользователь:** `aspect_db`
**Хост:** localhost:5432

**ВАЖНО:** Credentials (пароли) находятся в `.env` файле. Для подключения к БД используйте безопасные паттерны из `DB_ACCESS.md`.

---

## Основные таблицы

### services_catalog (68 услуг)

```sql
service_id          PK
scenario_name       VARCHAR
category_id         FK → ref_categories
object_id           FK → ref_objects
type_id             FK → ref_service_types
localization_id     FK → ref_localization
embedding_service   JSONB     -- Вектор услуги (256 float)
embedding_text      TEXT      -- Текст для векторизации
is_active           BOOLEAN
```

### ref_tags (350 тегов)

```sql
tag_id          PK
tag_name        VARCHAR
embedding_tag   JSONB     -- Вектор тега (256 float)
embedding_text  TEXT      -- Текст для векторизации
is_active       BOOLEAN
```

### service_tags (m:n связь, ~377 записей)

```sql
service_id  FK → services_catalog
tag_id      FK → ref_tags
```

---

## Справочники

### ref_service_types (типы услуг)

```sql
type_id     PK
type_name   VARCHAR  -- 'Инцидент', 'Плановые работы'
```

### ref_categories (категории)

```sql
category_id     PK
category_name   VARCHAR  -- 'Водоснабжение', 'Отопление', 'Электричество'
```

### ref_localization (локализация)

```sql
localization_id     PK
localization_name   VARCHAR  -- 'Индивидуальное', 'Общедомовое'
```

### ref_objects (объекты)

```sql
object_id     PK
object_name   VARCHAR  -- 'Квартира', 'Подъезд', 'Фасад'
```

---

## Пользователи и роли

### Роли в системе:
- **Житель** - доступ к личному кабинету
- **Пользователь УК** - функции УК, управление заявками
- **DBA** - управление пользователями, контроль данных
- **Администратор Django** - полный технический доступ

### Созданные пользователи:
- Администратор Django - смотри в Django таблице `auth_user`
- `Olga` - DBA
- `alex` - если создан

**ПРИМЕЧАНИЕ:** Пароли пользователей хранятся в БД и `.env` файле, НЕ в документации.

---

## Примеры SQL запросов

**ВАЖНО:** Для выполнения этих запросов используйте `bin/db_*.sh` wrappers. Подробности - в `DB_ACCESS.md`.

### Проверка структуры таблицы:
```bash
bin/db_read.sh "\d services_catalog"
```

### Поиск услуги по тексту:
```bash
bin/db_read.sh "
SELECT service_id, scenario_name, category_id
FROM services_catalog
WHERE scenario_name ILIKE '%труб%'
LIMIT 10;
"
```

### Создание пользователя PostgreSQL:
```bash
# От имени postgres
sudo -u postgres psql -c "CREATE USER aspect_alex WITH PASSWORD '...';"

# Выдача прав через wrapper
bin/db_write.sh --confirm "GRANT CONNECT ON DATABASE aspect_objects_db TO aspect_alex;"
```
