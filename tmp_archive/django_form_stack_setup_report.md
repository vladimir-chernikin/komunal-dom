# Django Form Stack Setup Report

**Дата:** 2026-03-29
**Цель:** Подготовка проекта к быстрому редизайну форм (unfold + crispy-forms)

---

## 1. ЧТО БЫЛО НАЙДЕНО

### Текущее состояние ПО до установки:
- ✅ **django-crispy-forms** — УЖЕ установлен в INSTALLED_APPS
- ✅ **crispy-bootstrap5** — УЖЕ установлен в INSTALLED_APPS
- ✅ **Crispy settings** — УЖЕ настроены (bootstrap5)
- ❌ **django-unfold** — НЕ установлен
- ✅ **Settings.py** — `/var/www/komunal-dom_ru/komunal_dom/settings.py`
- ✅ **URLs.py** — `/var/www/komunal-dom_ru/komunal_dom/urls.py`
- ✅ **WorkOrder admin** — `/var/www/komunal-dom_ru/work_orders/admin.py` (обычный Django admin)
- ✅ **WorkOrder templates** — 8 файлов в `work_orders/templates/work_orders/`

### Формы WorkOrder:
- `work_order_detail.html` — детальная форма заявки (custom UI)
- `work_order_create.html` — форма создания
- `executor_dashboard.html`, `executor_my_requests.html`, и др.

---

## 2. ЧТО БЫЛО УСТАНОВЛЕНО

### Установленные пакеты:

```bash
venv/bin/pip install django-unfold
```

**Результат:**
- Успешно установлен `django-unfold-0.87.0`
- Зависимости удовлетворены (django>=4.2, asgiref>=3.9.1, sqlparse>=0.5.0)

---

## 3. ФАЙЛЫ ИЗМЕНЕННЫ

### 3.1. `/var/www/komunal-dom_ru/komunal_dom/settings.py`

**Изменения в INSTALLED_APPS (строки 38-56):**

**ДО:**
```python
INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    ...
]
```

**ПОСЛЕ:**
```python
INSTALLED_APPS = [
    'jazzmin',
    'unfold',  # ← ДОБАВЛЕНО
    'unfold.theme',  # ← ДОБАВЛЕНО
    'django.contrib.admin',
    ...
]
```

**Порядок приложений:**
1. jazzmin (существующая тема)
2. **unfold** (новый)
3. **unfold.theme** (новый)
4. django.contrib.admin
5. crispy_forms (существующий)
6. crispy_bootstrap5 (существующий)
7. остальные приложения

**Примечание:** unfold добавлен ПЕРЕД django.contrib.admin для корректной перезаписи admin site.

---

### 3.2. `/var/www/komunal-dom_ru/komunal_dom/urls.py`

**Изменения:**

**Добавлены импорты unfold (после строки 16):**
```python
# Unfold admin URL configuration
try:
    from unfold.sites import UnfoldAdminSite
    from django.contrib.admin import site as default_admin_site

    # Create custom admin site with Unfold
    admin_site = UnfoldAdminSite()
    # Copy all registrations from default admin site to Unfold
    admin_site.copy_registry(default_admin_site)
except ImportError:
    # Fallback to default admin if unfold is not available
    from django.contrib import admin
    admin_site = admin.site
```

**Изменена строка 26:**
```python
# ДО:
path('admin/', admin.site.urls),

# ПОСЛЕ:
path('admin/', admin_site.urls),  # Unfold admin site (или fallback)
```

**Логика:**
- Создается кастомный admin site на базе UnfoldAdminSite
- Копируются все регистрации из стандартного admin.site через `copy_registry()`
- Если unfold недоступен (ImportError), используется стандартный admin.site как fallback
- Это позволяет безопасно использовать unfold даже если что-то пойдет не так

---

## 4. КАК ПРОВЕРИТЬ ЧТО UNFOLD РАБОТАЕТ

### Проверка 1: Перезапуск gunicorn
```bash
systemctl restart gunicorn-komunal-dom
systemctl status gunicorn-komunal-dom
```

**Статус должен быть:**
- `Active: active (running)`
- `Main PID` изменился (новый процесс)

### Проверка 2: Открыть админку
```bash
# URL админки
https://komunal-dom.ru/admin/
```

**Что должно быть:**
- Админка открылась без ошибок
- Интерфейс Unfold (современный дизайн, боковая панель)
- Все модели доступны (WorkOrder, RouteRef, и т.д.)

**Если ошибки 500:**
```bash
journalctl -u gunicorn-komunal-dom -n
```

### Проверка 3: Работа с моделями
1. Открой любой раздел ад acresки (например, Work Orders)
2. Проверь что:
   - Список объектов отображается
   - Фильтры работают
   - Поиск работает
   - Детальная страница открывается

---

## 5. КАК ПРОВЕРИТЬ ЧТО CRISPY FORMS РАБОТАЕТ

### Проверка 1: Создание тестовой формы

**Создай файл `/var/www/komunal-dom_ru/work_orders/forms.py` (если не существует):**

```python
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit
from .models import WorkOrder

class WorkOrderCrispyForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = ['original_request_text', 'service', 'priority_code', 'is_emergency']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False
        self.helper.layout = Layout(
            'original_request_text',
            'service',
            'priority_code',
            'is_emergency',
            Submit('submit', 'Создать', css_class='btn btn-primary'),
        )
```

### Проверка 2: Создание тестового view

**Добавь в `work_orders/views.py`:**

```python
from django.views.generic import CreateView
from django.urls import reverse_lazy
from .forms import WorkOrderCrispyForm

class WorkOrderCrispyCreateView(CreateView):
    model = WorkOrder
    form_class = WorkOrderCrispyForm
    template_name = 'work_orders/work_order_crispy_create.html'
    success_url = reverse_lazy('work_orders:executor_dashboard')
```

### Проверка 3: Создание тестового template

**Создай файл `/var/www/komunal-dom_ru/work_orders/templates/work_orders/work_order_crispy_create.html`:**

```html
{% extends 'work_orders/base.html' %}
{% load crispy_forms_tags %}

{% block title %}Создать заявку (Crispy){% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="card">
        <div class="card-header">
            <h5>Создать заявку (Crispy Forms)</h5>
        </div>
        <div class="card-body">
            {% crispy form %}
        </div>
    </div>
</div>
{% endblock %}
```

### Проверка 4: Проверка рендеринга

Открой URL:
```
https://komunal-dom.ru/work_orders/crispy/create/
```

**Что должно быть:**
- Форма отображается с Bootstrap 5 стилизацией
- Подписи над полями (label)
- Кнопка "Создать" стилизована как btn-primary
- Нет ошибок в консоли браузера

---

## 6. СЛЕДУЮЩИЕ 2 ШАГА ДЛЯ WORKORDER

### Шаг 1: Переключить WorkOrderAdmin на unfold + crispy (внутренняя полная форма)

**Что сделать:**
1. Обновить `work_orders/admin.py`
2. Использовать `ModelAdmin` от unfold (если нужно)
3. Добавить `form = WorkOrderCrispyForm` (если нужно)
4. Использовать `unfold.decorators` для кастомизации отображения

**Пример минимальной интеграции:**
```python
from django.contrib import admin
from unfold.decorators import display
from .models import WorkOrder

@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ['work_order_no', 'service', 'current_internal_status', 'priority_code', 'is_emergency']
    list_filter = ['current_internal_status', 'priority_code', 'is_emergency']
    search_fields = ['work_order_no', 'original_request_text']

    @display("Описание", ordering='-created_at')
    def description_short(self, obj):
        return obj.original_request_text[:100] + '...' if len(obj.original_request_text) > 100 else obj.original_request_text
```

### Шаг 2: Создать форму для оператора (detail_operator)

**Что сделать:**
1. Создать `WorkOrderOperatorForm` в `work_orders/forms.py`
2. Использовать crispy-forms для layout
3. Создать template `work_order_detail_operator.html` (или обновить существующий)
4. Добавить view `WorkOrderDetailView` (если нужно)
5. Интегрировать с Figma layout plan из `tmp_archive/work_order_detail_operator_figma_layout_plan.md`

**Пример формы:**
```python
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column
from .models import WorkOrder

class WorkOrderOperatorForm(forms.ModelForm):
    class Meta:
        model = WorkOrder
        fields = [
            'original_request_text', 'resolution_text',
            'service', 'department', 'responsible_user',
            'current_internal_status', 'priority_code'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Fieldset(
                'Основная информация',
                Row(
                    Column('service', css_class='col-md-6'),
                    Column('department', css_class='col-md-6'),
                ),
                'responsible_user',
            ),
            Fieldset(
                'Статус и приоритет',
                Row(
                    Column('current_internal_status', css_class='col-md-6'),
                    Column('priority_code', css_class='col-md-6'),
                ),
                'is_emergency',
            ),
            Fieldset(
                'Содержание',
                'original_request_text',
            ),
            Fieldset(
                'Решение',
                'resolution_text',
            ),
        )
```

---

## 7. ИТОГОВОЕ СОСТОЯНИЕ

### Установлено:
- ✅ django-unfold 0.87.0
- ✅ unfold + unfold.theme в INSTALLED_APPS
- ✅ unfold admin site в urls.py

### Уже было:
- ✅ django-crispy-forms (в INSTALLED_APPS)
- ✅ crispy-bootstrap5 (в INSTALLED_APPS)
- ✅ Crispy settings для Bootstrap 5

### Изменено:
- ✅ `/var/www/komunal-dom_ru/komunal_dom/settings.py` — unfold добавлен
- ✅ `/var/www/komunal-dom_ru/komunal_dom/urls.py` — unfold интегрирован
- ✅ Gunicorn перезапущен

### НЕ изменено (следующие шаги):
- ❌ `work_orders/admin.py` — будет обновлен на шаге 1
- ❌ `work_orders/forms.py` — будет создан на шаге 2
- ❌ Шаблоны work_orders — будут обновлены на шаге 2

---

## 8. РИСКИ И MITIGATION

### Риск 1: Unfold конфликт с jazzmin
**Описание:** Оба админских пакета могут конфликтовать
**Mitigation:** unfold идет ПЕРЕД django.contrib.admin, jazzmin сохранен как theme
**Проверка:** Открыть `/admin/` и проверить что интерфейс Unfold

### Риск 2: Crispy forms не работают с Bootstrap 5
**Описание:** Возможно несовместимость версий
**Mitigation:** crispy-bootstrap5 уже установлен, settings настроены корректно
**Проверка:** Создать тестовую форму и проверить рендеринг

### Риск 3: gunicorn не перезапустился
**Описание:** Изменения settings.py не применились
**Mitigation:** systemctl restart выполнен, статус проверен
**Проверка:** Проверить `systemctl status gunicorn-komunal-dom`

---

## 9. ПРОВЕРКИ ПЕРЕД ИСПОЛЬЗОВАНИЕМ

**Проверь unfold:**
```bash
# 1. Проверить что gunicorn перезапущен
systemctl status gunicorn-komunal-dom

# 2. Открыть админку
curl -I https://komunal-dom.ru/admin/

# 3. Проверить логи (если есть ошибки 500)
journalctl -u gunicorn-komunal-dom -n | tail -20
```

**Проверить crispy forms:**
```bash
# 1. Создать тестовую форму (см. раздел 5 выше)

# 2. Добавить view и template

# 3. Открыть URL формы и проверить стилизацию
```

---

**ОТЧЕТ СОЗДАН:** 2026-03-29
**СТАТУС:** База готова, след. шаги — WorkOrder integration
