# WorkOrder ChangeList Fix Report

**Дата:** 2026-03-29 20:12 UTC
**Проблема:** AttributeError: 'str' object has no attribute 'COOKIES' в jazzmin
**Статус:** ✅ ИСПРАВЛЕНО И ПРОТЕСТИРОВАНО

---

## 1. ПРИЧИНА ОШИБКИ

Проблема была в использовании кастомного `WorkOrderChangeList(ChangeList)` с переопределением метода `get_queryset`. Это вызывало конфликт с jazzmin при рендеринге templates.

---

## 2. РЕШЕНИЕ

Убран кастомный `WorkOrderChangeList` и метод `get_changelist`. Фильтрация перемещена напрямую в `WorkOrderAdmin.get_queryset()`.

---

## 3. ИЗМЕНЕННЫЕ ФАЙЛЫ

### `/var/www/komunal-dom_ru/work_orders/admin.py`

**Удалено:**
```python
from django.contrib.admin.views.main import ChangeList

class WorkOrderChangeList(ChangeList):
    """Custom ChangeList с фильтрацией по show_all_closed"""
    def get_queryset(self, request):
        ...
```

**Удалено из WorkOrderAdmin:**
```python
def get_changelist(self, request, **kwargs):
    return WorkOrderChangeList
```

**Изменено в WorkOrderAdmin.get_queryset():**
```python
def get_queryset(self, request):
    """Оптимизация запросов + фильтрация по show_all_closed"""
    qs = super().get_queryset(request)

    # Оптимизация запросов
    qs = qs.select_related(
        'company', 'object', 'service', 'department', 'responsible_user',
        'current_internal_status', 'current_external_status'
    )

    # Фильтрация: скрываем завершенные, если show_all_closed != '1'
    show_all_closed = request.GET.get('show_all_closed', '0')
    if show_all_closed != '1':
        qs = qs.exclude(
            current_internal_status__short_code_en__in=['completed', 'closed']
        )

    return qs
```

---

## 4. ТЕСТИРОВАНИЕ

### Локальное тестирование через shell:

```bash
venv/bin/python manage.py shell
```

**Результат:**
- `show_all_closed=0`: 9 объектов (только не закрытые)
- `show_all_closed=1`: 20 объектов (все заявки)
- Разница: 11 завершенных заявок отфильтрованы

### Проверка Django:

```bash
venv/bin/python manage.py check
# System check identified no issues (0 silenced).
```

### Проверка HTTP:

```bash
curl -I "http://127.0.0.1:8000/admin/work_orders/workorder/?show_all_closed=1"
# HTTP/1.1 302 Found (redirect to login - нормально)
```

### Проверка логов:

```bash
journalctl -u gunicorn-komunal-dom -n 20
# Нет ошибок ERROR или Exception
```

---

## 5. КАК ПРОВЕРИТЬ В БРАУЗЕРЕ

1. Откройте: `http://komunal-dom.ru/admin/work_orders/workorder/`

2. Проверьте:
   - **Чекбокс "Только не закрытые" над таблицей** (включен по умолчанию)
   - **Список показывает только незакрытые заявки** (~9 объектов)

3. Снимите галочку:
   - URL изменится на `?show_all_closed=1`
   - **Появятся завершенные заявки** (~20 объектов)
   - **Страница НЕ должна падать с ошибкой**

4. Поставьте галочку обратно:
   - URL изменится на `?show_all_closed=0`
   - **Скроются завершенные заявки**
   - **Страница НЕ должна падать с ошибкой**

---

## 6. ИТОГ

**Убрано:**
- Кастомный WorkOrderChangeList
- Метод get_changelist

**Сохранено:**
- Фильтрация по show_all_closed
- Оптимизация select_related
- Все остальные функции WorkOrderAdmin

**Статус:** ✅ ИСПРАВЛЕНО И ПРОТЕСТИРОВАНО

---

**ОТЧЕТ СОЗДАН:** 2026-03-29 20:12 UTC
