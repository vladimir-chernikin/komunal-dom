# Admin 502 Recovery Report

**Дата:** 2026-03-29 13:07 UTC
**Инцидент:** 502 Bad Gateway на `/admin/` после интеграции django-unfold
**Статус:** ✅ RECOVERED

---

## 1. ПРИЧИНА АВАРИИ

### Корневая причина:

**Ошибка 1:** `ModuleNotFoundError: No module named 'unfold.theme'`
- В `settings.py` был добавлен несуществующий модуль `'unfold.theme'` в INSTALLED_APPS
- Пакет `django-unfold` НЕ содержит модуля `unfold.theme`
- В INSTALLED_APPS нужно добавлять только `'unfold'`

**Ошибка 2:** `AttributeError: 'UnfoldAdminSite' object has no attribute 'copy_registry'`
- В `urls.py` использовался несуществующий метод `admin_site.copy_registry()`
- Класс `UnfoldAdminSite` не имеет этого метода
- Попытка использовать Django pattern для копирования регистраций admin site

### Итог:
Gunicorn workers падали при старте с `ModuleNotFoundError`, сайт отдавал 502 Bad Gateway.

---

## 2. КОМАНДЫ ВЫПОЛНЕННЫ

### Диагностика:

```bash
# Проверка статуса gunicorn
systemctl status gunicorn-komunal-dom --no-pager -l

# Проверка логов gunicorn
journalctl -u gunicorn-komunal-dom -n 50 --no-pager

# Проверка nginx error log
tail -50 /var/log/nginx/error.log

# Проверка установленных пакетов
venv/bin/pip list | grep -i unfold

# Проверка структуры unfold
ls -la venv/lib/python3.12/site-packages/unfold/

# Проверка модулей unfold
venv/bin/python -c "import unfold; import pkgutil; print([m.name for m in pkgutil.iter_modules(unfold.__path__)])"
```

### Восстановление:

```bash
# 1. Rollback settings.py - удаление unfold.theme
# Выполнено через Edit tool

# 2. Rollback urls.py - возврат к стандартному admin.site
# Выполнено через Edit tool

# 3. Перезапуск gunicorn
systemctl restart gunicorn-komunal-dom

# 4. Проверка статуса
systemctl status gunicorn-komunal-dom --no-pager -l

# 5. Проверка Django
venv/bin/python manage.py check

# 6. Проверка HTTP ответов
curl -I http://127.0.0.1:8000/admin/
curl -I http://127.0.0.1:8000/
```

---

## 3. ОШИБКИ НАЙДЕНЫ

### Ошибка 1: ModuleNotFoundError

**Log:**
```
Mar 29 13:04:04 komunaldom gunicorn_start.sh[3940141]: ModuleNotFoundError: No module named 'unfold.theme'
```

**Причина:** Добавлен несуществующий модуль в INSTALLED_APPS

**Исправление:** Удалена строка `'unfold.theme'` из settings.py

---

### Ошибка 2: AttributeError

**Log:**
```
AttributeError: 'UnfoldAdminSite' object has no attribute 'copy_registry'. Did you mean: '_registry'?
```

**Причина:** Использован несуществующий метод для копирования регистраций admin site

**Исправление:** Возврат к стандартному `admin.site` в urls.py

---

## 4. ФАЙЛЫ ИЗМЕНЕНЫ

### `/var/www/komunal-dom_ru/komunal_dom/settings.py`

**Удалено:**
```python
'unfold.theme',  # Тема для Unfold
```

**Из INSTALLED_APPS:**
```python
# ДО (неверно):
INSTALLED_APPS = [
    'jazzmin',
    'unfold',
    'unfold.theme',  # ← ОШИБКА: этого модуля не существует
    'django.contrib.admin',
    ...
]

# ПОСЛЕ (правильно):
INSTALLED_APPS = [
    'jazzmin',
    'unfold',  # ← Только unfold, без unfold.theme
    'django.contrib.admin',
    ...
]
```

---

### `/var/www/komunal-dom_ru/komunal_dom/urls.py`

**Изменено:**
```python
# ДО (неверно):
# Unfold admin URL configuration
try:
    from unfold.sites import UnfoldAdminSite
    from django.contrib.admin import site as default_admin_site

    # Create custom admin site with Unfold
    admin_site = UnfoldAdminSite()
    # Copy all registrations from default admin site to Unfold
    admin_site.copy_registry(default_admin_site)  # ← ОШИБКА: метод не существует
except ImportError:
    from django.contrib import admin
    admin_site = admin.site

# ПОСЛЕ (правильно):
# Admin site configuration (standard Django admin)
from django.contrib import admin
admin_site = admin.site
```

**Логика:** Возврат к стандартному Django admin.site, unfold пока не используется.

---

## 5. ИТОГ ПРОВЕРКИ ПОСЛЕ ИСПРАВЛЕНИЯ

### Gunicorn статус:
```
Active: active (running)
Main PID: 3940854 (gunicorn)
Tasks: 7 (limit: 9484)
Memory: 135.2M (peak: 135.4M)
```

**Все 3 worker'а запустились успешно:**
- Worker 1: PID 3940888
- Worker 2: PID 3940889
- Worker 3: PID 3940890

### Django check:
```bash
venv/bin/python manage.py check
# System check identified no issues (0 silenced).
```

### HTTP ответы:

**/admin/**
```
HTTP/1.1 302 Found
Location: /admin/login/?next=/admin/
```
✅ Работает (redirect to login)

**Главная страница**
```
HTTP/1.1 200 OK
```
✅ Работает

---

## 6. ЧТО ДЕЛАТЬ ДАЛЬШЕ

### Чтобы подключить unfold без падения сайта:

**Шаг 1: Изучить документацию django-unfold**
- Прочитать https://django-unfold.dev/
- Понять правильный способ интеграции UnfoldAdminSite
- Изучить как работать с существующими admin.py регистрациями

**Шаг 2: Правильная интеграция UnfoldAdminSite**

Варианты:
1. **Использовать unfold только как template_override** (без UnfoldAdminSite)
2. **Перерегистрировать все ModelAdmin классы** для UnfoldAdminSite
3. **Найти правильный способ миграции** с admin.site на UnfoldAdminSite

**Шаг 3: Тестирование в dev окружении**
- Создать тестовую ветку
- Применить изменения unfold
- Проверить что все admin модели работают
- Только после этого deployment в production

**Шаг 4: Постепенная миграция**
- НЕ менять всё сразу
- Начать с одного приложения (например, work_orders)
- Проверить работу
- Расширять на остальные приложения

---

## 7. УРОКИ

1. **Всегда проверять структуру пакета** перед добавлением в INSTALLED_APPS
2. **Не использовать методы без проверки** их существования в документации
3. **Тестировать в dev окружении** перед изменением production
4. **Создавать rollback plan** перед изменениями критичных компонентов
5. ** unfold требует осторожности** при интеграции с существующим Django admin

---

## 8. ТЕКУЩЕЕ СОСТОЯНИЕ

### Установлено:
- ✅ django-unfold 0.87.0 (в venv)
- ✅ unfold в INSTALLED_APPS

### НЕ работает:
- ❌ UnfoldAdminSite (не используется в urls.py)
- ❌ unfold.theme (модуль не существует)

### Работает:
- ✅ Стандартный Django admin (admin.site)
- ✅ jazzmin (тема админки)
- ✅ Все остальные приложения

### Статус: RECOVERED ✅

Сайт работает, /admin/ доступен, никаких ошибок в логах.

---

**ОТЧЕТ СОЗДАН:** 2026-03-29 13:07 UTC
**ИНЦИДЕНТ ЗАКРЫТ:** Сайт восстановлен
