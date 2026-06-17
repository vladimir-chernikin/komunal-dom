# RUNTIME_DEPLOY_OPERATIONS - Коммунальный Дом

**Дата:** 2026-03-19
**Окружение:** Production (Ubuntu server, ручной деплой)

---

## 1. RUNTIME-КАРТИНА ПРОЕКТА

### Стек:

| Компонент | Версия | Назначение |
|---|---|---|
| **ОС** | Ubuntu server | Базовая ОС |
| **Web-сервер** | nginx (порт 80) | Обработка HTTP запросов |
| **App-сервер** | gunicorn (3 workers) | WSGI приложение |
| **Фреймворк** | Django 6.0 | Web-фреймворк |
| **База данных** | PostgreSQL 16 | Хранение данных |
| **Python** | venv | Виртуальное окружение |

### Процесс:

```
┌─────────────┐
│  nginx      │ (порт 80)
│  proxy      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  gunicorn   │ (127.0.0.1:8000, 3 workers)
│  3 workers  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Django     │
│  6.0        │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ PostgreSQL  │
│  localhost:5432 │
└─────────────┘
```

---

## 2. SYSTEMD СЕРВИСЫ

### Gunicorn (web-сервер)

**Файл:** `/etc/systemd/system/gunicorn-komunal-dom.service`

**Управление:**
```bash
# Перезапуск (после изменений .py файлов)
systemctl restart gunicorn-komunal-dom

# Проверка статуса
systemctl status gunicorn-komunal-dom

# Просмотр логов
journalctl -u gunicorn-komunal-dom -f

# Перезагрузка (если изменилась конфигурация)
systemctl daemon-reload
```

**КОГДА НУЖЕН RESTART:**
- ✅ После изменений `.py` файлов (views, models, services)
- ✅ После изменений настроек Django
- ✅ После добавления новых Django приложений

**КОГДА НЕ НУЖЕН RESTART:**
- ❌ Изменения `.html` шаблонов (nginx отдает напрямую)
- ❌ Изменения статических файлов

### Enhanced Aspect Bot (Telegram бот)

**Файл:** `/etc/systemd/system/enhanced-aspect-bot.service`

**Управление:**
```bash
# Перезапуск
systemctl restart enhanced-aspect-bot

# Проверка статуса
systemctl status enhanced-aspect-bot

# Просмотр логов
journalctl -u enhanced-aspect-bot -f
```

**Исполняемый файл:** `/var/www/komunal-dom_ru/enhanced_aspect_bot.py`

---

## 3. NGINX

### Конфигурация:

**Файл:** `/etc/nginx/sites-enabled/komunal-dom.ru`

**Основные директивы:**
- `listen 80` - порт 80
- `server_name komunal-dom.ru www.komunal-dom.ru`
- `proxy_pass http://127.0.0.1:8000` - прокси на gunicorn

### Управление:

```bash
# Проверка конфигурации
nginx -t

# Перезагрузка (без разрыва соединений)
systemctl reload nginx

# Полный перезапуск
systemctl restart nginx

# Проверка статуса
systemctl status nginx
```

**КОГДА НУЖЕН RELOAD:**
- ✅ После изменений nginx конфигурации

**КОГДА НУЖЕН RESTART:**
- ✅ После серьезных изменений конфигурации

---

## 4. DJANGO УПРАВЛЕНИЕ

### Рабочая директория:

```bash
cd /var/www/komunal-dom_ru
source venv/bin/activate
```

### Команды:

| Команда | Назначение | КОГДА использовать |
|---|---|---|
| `./manage.py run` | Запуск dev-сервера | Разработка |
| `./manage.py migrate` | Миграции БД | После изменений models.py |
| `./manage.py makemigrations` | Создание миграций | После изменений models.py |
| `./manage.py collectstatic` | Сбор статики | После добавления статических файлов |
| `./manage.py shell` | Django shell | Отладка |
| `./manage.py createsuperuser` | Создание суперпользователя | Начальная настройка |

### Alias (manage.sh):

В проекте есть `manage.sh` - обертка над manage.py:

```bash
./manage.sh run              # Запуск
./manage.sh migrate          # Миграции
./manage.sh shell            # Shell
```

---

## 5. КОГДА НУЖЕН MIGRATE

**НУЖЕН MIGRATE:**
- ✅ После изменений models.py
- ✅ После добавления новых Django приложений
- ✅ После создания новых моделей

**НЕ НУЖЕН MIGRATE:**
- ❌ После изменений views.py, urls.py, templates
- ❌ После изменений сервисов (.py файлы в корне)

**ОБЯЗАТЕЛЬНЫЙ ЧЕК-ЛИСТ:**
```bash
# 1. Создать миграции
./manage.py makemigrations

# 2. Проверить миграции
./manage.py showmigrations

# 3. Сделать backup БД (ПЕРЕД migrate!)
pg_dump -U aspect_db aspect_objects_db > backup_before_migration.dump

# 4. Применить миграции
./manage.py migrate

# 5. Проверить результат
./manage.py showmigrations
```

---

## 6. КОГДА НУЖЕН COLLECTSTATIC

**НУЖЕН COLLECTSTATIC:**
- ✅ После добавления/изменения статических файлов
- ✅ После изменения STATIC settings
- ✅ После изменений в static/

**НЕ НУЖЕН COLLECTSTATIC:**
- ❌ После изменений .py файлов (кроме settings.py)
- ❌ После изменений templates/

**ОБЯЗАТЕЛЬНЫЙ ЧЕК-ЛИСТ:**
```bash
# 1. Собрать статику
./manage.py collectstatic --noinput

# 2. Проверить права
chmod -R 755 staticfiles/

# 3. Перезапустить nginx (если нужно)
systemctl reload nginx
```

---

## 7. ПРАВА ДОСТУПА

### После создания файлов через Write tool:

```bash
# Для Django шаблонов
chmod 644 файл.html
chown olga:www-data файл.html

# Для статических файлов
chmod 644 файл.css
chown olga:www-data файл.css

# Для /tmp файлов (для веб-интерфейса)
chmod 644 /tmp/файл
```

### Владелец и группа:

| Тип файла | Владелец | Группа | Права |
|---|---|---|---|
| Django templates | olga | www-data | 644 |
| Статические файлы | olga | www-data | 644 |
| .py файлы | olga | www-data | 644 |
| /tmp файлы | olga | www-data | 644 |

### Проверка:

```bash
# Проверить владельца и права
ls -la файл

# Исправить если нужно
chown olga:www-data файл
chmod 644 файл
```

---

## 8. СЕКРЕТЫ (.env)

**Файл:** `/var/www/komunal-dom_ru/.env`

**Основные переменные:**

| Переменная | Назначение |
|---|---|
| `SECRET_KEY` | Секретный ключ Django |
| `DEBUG` | Режим отладки (False в production) |
| `DB_NAME` | Имя БД (aspect_objects_db) |
| `DB_USER` | Пользователь БД (aspect_db) |
| `DB_PASSWORD` | Пароль БД (смотри в `.env` файле) |
| `DB_HOST` | Хост БД (localhost) |
| `DB_PORT` | Порт БД (5432) |
| `YANDEX_GPT_API_KEY` | API ключ YandexGPT |
| `YANDEX_EMBEDDINGS_API_KEY` | API ключ Yandex Embeddings |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота |

**ПРАВИЛО:** Никогда не коммитить .env в git! Реальные credentials только в `.env`, НЕ в документации.

---

## 9. ЛОГИ

### Django логи:

**Расположение:** `/var/www/komunal-dom_ru/logs/`

**Просмотр:**
```bash
tail -f logs/django.log
tail -f logs/debug.log
```

### Systemd логи:

```bash
# Gunicorn
journalctl -u gunicorn-komunal-dom -f

# Enhanced Aspect Bot
journalctl -u enhanced-aspect-bot -f

# Nginx
journalctl -u nginx -f
```

### Nginx логи:

**Расположение:** `/var/log/nginx/`

```bash
# Access лог
tail -f /var/log/nginx/access.log

# Error лог
tail -f /var/log/nginx/error.log
```

---

## 10. БЭКАПЫ

### Бэкапы БД:

**Расположение:** `/var/www/komunal-dom_ru/backups/`

**Файлы:**
- `aspect_objects_db_20260313_134739.dump`
- `aspect_objects_db_20260313_134815.dump`
- `aspect_objects_db_BEFORE_MIGRATION_20260313_063237.dump`
- `before_drop_old_tables_20260317_0826.dump`

**Создание бэкапа:**
```bash
pg_dump -U aspect_db aspect_objects_db > backup_$(date +%Y%m%d_%H%M%S).dump
```

**Восстановление из бэкапа:**
```bash
psql -U aspect_db aspect_objects_db < backup.dump
```

### Рудиментные бэкапы:

**Директории:**
- `/var/www/komunal-dom_ru/backups_20260223/` - старые бэкапы (РУДИМЕНТ?)
- `/var/www/komunal-dom_ru/backups_20260223_133420/` - старые бэкапы (РУДИМЕНТ?)

**Рекомендация:** Оставить только последние 3 бэкапа, остальные архивировать

---

## 11. URL И ДОСТУПЫ

### Основные URL:

| URL | Назначение |
|---|---|
| `http://komunal-dom.ru/` | Главная страница |
| `http://komunal-dom.ru/admin/` | Админка Django |
| `http://komunal-dom.ru/files/` | Файловый менеджер |
| `http://komunal-dom.ru/chat/` | Веб-чат (требуется авторизация) |
| `http://komunal-dom.ru/llm-tester/` | LLM Tester |
| `http://komunal-dom.ru/db-sql/` | СУБД SQL интерфейс |
| `http://aspect.komunal-dom.ru/` | Поддомен (если настроен) |

### Пользователи:

| Пользователь | Пароль | Роль |
|---|---|---|
| `Admin_Aspect` | смотри в `.env` / Django `auth_user` таблице | Django Administrator |
| `Olga` | смотри в `.env` / Django `auth_user` таблице | DBA |
| `alex` | смотри в `.env` / Django `auth_user` таблице | если создан |

**ПРИМЕЧАНИЕ:** Реальные пароли пользователей хранятся в БД и `.env` файле, НЕ в документации.

---

## 12. ВАЖНЫЕ КОМАНДЫ ДЛЯ PROD

### Проверка статуса:

```bash
# Проверить все сервисы
systemctl status gunicorn-komunal-dom
systemctl status nginx
systemctl status enhanced-aspect-bot

# Проверить, что gunicorn запущен
ps aux | grep gunicorn

# Проверить порт 8000
netstat -tlnp | grep 8000
```

### Перезапуск после изменений .py:

```bash
# 1. Изменить .py файл

# 2. Перезапустить gunicorn
systemctl restart gunicorn-komunal-dom

# 3. Проверить статус
systemctl status gunicorn-komunal-dom --no-pager -l | head -15

# 4. Проверить логи
journalctl -u gunicorn-komunal-dom -n 50
```

### Полный деплой (после множественных изменений):

```bash
# 1. Собрать факты
git status
git diff

# 2. Применить миграции (если нужно)
./manage.py migrate

# 3. Собрать статику (если нужно)
./manage.py collectstatic --noinput

# 4. Перезапустить gunicorn
systemctl restart gunicorn-komunal-dom

# 5. Перезагрузить nginx (если нужно)
systemctl reload nginx

# 6. Проверить статус
systemctl status gunicorn-komunal-dom nginx
```

---

## 13. ПОДдомены

### SubdomainMiddleware:

**Файл:** `komunal_dom/middleware.py`

**Назначение:** Обработка поддоменов

**Известные поддомены:**
- `aspect.komunal-dom.ru` - aspect поддомен (если настроен)

**Проверка:**
```bash
# Проверить DNS
nslookup aspect.komunal-dom.ru

# Проверить nginx конфигурацию
grep -r "aspect.komunal-dom.ru" /etc/nginx/
```

---

## 14. ЧТО НУЖНО ПОМНИТЬ ПРИ РУЧНОМ ДЕПЛОЕ

### Обязательный чек-лист:

1. **Проверить git status** - что изменилось?
2. **Сделать backup БД** - перед миграциями
3. **Применить миграции** - если изменились models.py
4. **Собрать статику** - если изменились статические файлы
5. **Перезапустить gunicorn** - если изменились .py файлы
6. **Перезагрузить nginx** - если изменилась конфигурация
7. **Проверить права** - на новые файлы
8. **Проверить логи** - нет ли ошибок

### Частые ошибки:

1. **Забыли перезапустить gunicorn** - изменения .py не применяются
2. **Забыли применить миграции** - БД рассинхронизирована
3. **Забыли собрать статику** - статические файлы не обновляются
4. **Забыли установить права** - nginx/gunicorn не может читать файлы
5. **Сделали restart вместо reload** - разрыв соединений (nginx)

---

## 15. РЕКОМЕНДАЦИИ

### Минимальные улучшения:

1. **Автоматизировать бэкапы** - cron для ежедневных бэкапов БД
2. **Очистить старые бэкапы** - оставить только последние 3
3. **Добавить логирование** - для отладки production проблем

### Средние улучшения:

1. **Автоматизированный деплой** - CI/CD пайплайн
2. **Мониторинг** - Prometheus/Grafana для метрик
3. **Алертинг** - уведомления о проблемах

### Сложные улучшения:

1. **Контейнеризация** - Docker для упрощения деплоя
2. **Kubernetes** - для масштабирования
3. **Zero-downtime deployment** -滚动 обновления

---

**ВЫВОД:** Проект имеет простую runtime-конфигурацию (nginx + gunicorn + PostgreSQL), но страдает от отсутствия автоматизации (ручной деплой) и множественных бэкапов. Главные проблемы: забывают перезапускать gunicorn после изменений .py, нет автоматизированных бэкапов. Quick wins: настроить автоматические бэкапы, очистить старые бэкапы, добавить чек-лист деплоя.
