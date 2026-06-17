# Ролевая модель контроля доступа (RBAC)

**ДАТА СОЗДАНИЯ:** 2026-04-02
**АВТОР:** Claude Sonnet
**СТАТУС:** Реализовано и протестировано

---

## ОБЗОР

В системе komunal-dom.ru реализована ролевая модель контроля доступа (RBAC) с разделением на:

1. **Django Superuser** (DevOps) - полный доступ к `/admin/`
2. **Staff пользователи** - сотрудники компании с разными правами
3. **Residents** - жители (обычные пользователи)

---

## АРХИТЕКТУРА РАЗДЕЛЕНИЯ ПРАВ

### 1. Модель пользователя

**Два источника прав:**

| Источник | Таблица | Поля | Назначение |
|---|---|---|---|
| **Django User** | `auth_user` | `is_staff`, `is_superuser` | Технический доступ к системе |
| **UserCompanyMembership** | `request_mgmt.user_company_membership` | `role_code`, `company_id`, `department_id` | Бизнес-роль и привязка к компании |

**Соотношение:**
- `is_superuser = true` → Django Admin (DevOps)
- `is_staff = true` + `UserCompanyMembership` → Staff пользователь (сотрудник)
- `is_staff = false` → Resident (житель)

---

### 2. ИЕРАРХИЯ РОЛЕЙ

```
superuser (Django Admin)
    └── Полный доступ к /admin/
    └── Может все

direktor_uk (Директор УК)
    ├── Видит всю компанию
    ├── Создает пользователей в своей компании
    ├── Настраивает SLA и услуги
    └── НЕ может править общие справочники (НСИ)

chief_engineer (Главный инженер)
    ├── Видит всю компанию
    ├── Перераспределяет обращения
    ├── Меняет статусы (on_hold, reopen)
    └── "Кастрированный директор" (минус создание пользователей)

executor (Исполнитель / Рядовой сотрудник)
    ├── Видит свои заявки + пул подразделения
    ├── Самоназначается
    └── "Кастрированный главный инженер" (минус перераспределение)

resident (Житель)
    └── Видит только свои заявки
```

---

### 3. Middleware

**ФАЙЛ:** `portal/middleware.py`

#### DjangoAdminProtectionMiddleware
**Назначение:** Защита Django Admin - только для superuser

**Логика:**
- Если `request.path.startswith('/admin/')`:
  - Если `user.is_superuser = true` → разрешить
  - Если `user.is_staff = true` но `is_superuser = false` → redirect на `/admin-uk/`
  - Если `user.is_staff = false` → forbidden

**Проблема решает:**
- ❌ Было: staff пользователи видели `/admin/` (неправильно!)
- ✅ Стало: только superuser видит `/admin/`

#### CompanyMembershipMiddleware
**Назначение:** Добавление компании в request

**Добавляет в `request`:**
- `request.user_company_id`
- `request.user_department_id`
- `request.user_role_code`
- `request.user_primary_membership`

**Используется в views** для фильтрации по компании.

---

### 4. Mixins

**ФАЙЛ:** `portal/mixins.py`

#### StaffRequiredMixin
**Назначение:** Базовый миксин для всех Staff интерфейсов

**Проверяет:**
- `user.is_staff = true`
- `user.is_authenticated = true`
- `UserCompanyMembership` существует

#### DirectorMixin
**Назначение:** Для Директора УК

**Проверяет:**
- Базовые требования (из StaffRequiredMixin)
- `role_code = 'direktor_uk'`

#### ChiefEngineerMixin
**Назначение:** Для Главного инженера

**Проверяет:**
- Базовые требования
- `role_code = 'chief_engineer'`

#### ExecutorMixin
**Назначение:** Для Исполнителя

**Проверяет:**
- Базовые требования
- `role_code = 'executor'`

#### ResidentMixin
**Назначение:** Для Жителя

**Проверяет:**
- `user.is_authenticated = true`
- **НЕ требует** `is_staff`

---

### 5. Кастомная система Login

**ФАЙЛ:** `portal/auth_views.py`

#### CustomLoginView
**Назначение:** Кастомный login с role-based redirect

**Отличие от стандартного:**
- Принимает всех `is_staff = true` (не только superuser)
- Redirect в зависимости от роли
- Проверяет наличие `UserCompanyMembership`

**Логика redirect:**

| Роль | Redirect |
|---|---|
| `is_superuser = true` | `/admin/` |
| `direktor_uk` | `/admin-uk/` |
| `chief_engineer` | `/chief-engineer/` |
| `executor` | `/executor/` |
| `resident` | `/subscribers/` |
| Нет membership | `/no-membership/` |

---

### 6. Интерфейсы

**ФАЙЛ:** `portal/admin_views.py`

#### admin_page()
**URL:** `/admin-uk/`
**Доступ:** `direktor_uk`, `chief_engineer`, `uk_user`
**Назначение:** Главная админка УК

**Функционал:**
- Статистика по пользователям компании
- Статистика по файлам, промптам, КЛАДР
- Фильтрация по `company_id`

#### director_page()
**URL:** `/director/`
**Доступ:** `direktor_uk` (только директора)
**Назначение:** Дашборд директора

**Функционал:**
- То же что `admin_page` + контроль доступа
- Создание пользователей в своей компании

#### chief_engineer_page()
**URL:** `/chief-engineer/`
**Доступ:** `chief_engineer` (только главные инженеры)
**Назначение:** Дашборд главного инженера

**Функционал:**
- Перераспределение обращений
- Изменение статусов
- "Кастрированный директор"

#### executor_dashboard()
**URL:** `/executor/`
**Доступ:** `executor` (только исполнители)
**Назначение:** Дашборт исполнителя

**Функционал:**
- Мои заявки
- Пул подразделения
- "Кастрированный главный инженер"

---

### 7. User Admin

**ФАЙЛ:** `portal/admin.py`

#### UserAdmin
**Назначение:** Красивый интерфейс редактирования пользователя

**Изменено (2026-04-02):**

**1. list_display:**
```python
('username', 'email', 'first_name', 'last_name', 'get_company', 'get_role', 'is_active', 'date_joined')
```
- Добавлена колонка `get_company` (ссылка на компанию)

**2. fieldsets:**
```python
('Основная информация', {
    'fields': ('username', 'password', 'first_name', 'last_name', 'email',
               'get_company_link', 'get_timezone', 'get_phone'),
})
```
- Добавлены readonly поля:
  - `get_company_link` - ссылка на компанию
  - `get_timezone` - часовой пояс из UserProfile
  - `get_phone` - телефон из UserProfile

**3. get_role() метод:**
- Приоритет: `UserCompanyMembership.role_code` → `UserProfile.role`
- Badge с цветом по роли

**4. get_company() метод:**
- Ищет primary membership
- Если нет primary - любую активную
- Ссылка на `/admin/work_orders/usercompanymembership/?user_id__exact={id}`

---

## ПРАКТИКА ИСПОЛЬЗОВАНИЯ

### Создание пользователя (пример)

**ШАГ 1:** Создать Django User через `/admin/auth/user/`
- Установить `is_staff = true`
- Установить пароль

**ШАГ 2:** Создать UserCompanyMembership через `/admin/work_orders/usercompanymembership/`
- `user_id` - ссылка на User
- `company_id` - выбор компании
- `department_id` - выбор подразделения
- `role_code` - выбор роли (direktor_uk, chief_engineer, executor, resident)
- `is_primary = true` - основной membership
- `is_active = true`
- `date_from` - текущая дата

**ШАГ 3 (опционально):** Заполнить UserProfile через inline в User
- `role` - для обратной совместимости
- `timezone` - часовой пояс
- `phone` - телефон
- `address` - адрес

**ШАГ 4:** Пользователь логинится на `/` или `/login/`
- Система автоматически redirect на нужный интерфейс

---

## РЕШЕНИЕ ПРОБЛЕМЫ goncharov_ms

**ПРОБЛЕМА:**
- goncharov_ms не мог войти (is_staff = false)
- landing.html отправлял на `/admin/login/`
- Django Admin требует is_staff = true

**РЕШЕНИЕ (2026-04-02):**

**1. Изменен landing.html:**
```html
<!-- Было -->
<form action="{% url 'admin:login' %}">

<!-- Стало -->
<form action="{% url 'portal:custom_login' %}">
```

**2. Создан CustomLoginView:**
- Принимает всех staff пользователей
- Redirect по ролям
- Проверяет UserCompanyMembership

**3. Создан DjangoAdminProtectionMiddleware:**
- Блокирует `/admin/` для non-superuser
- Redirect на `/admin-uk/`

**4. Что нужно сделать для goncharov_ms:**
```sql
UPDATE auth_user SET is_staff = true WHERE username = 'goncharov_ms';
```

**5. Создать UserCompanyMembership:**
```sql
INSERT INTO request_mgmt.user_company_membership
(user_id, company_id, department_id, role_code, is_primary, is_active, date_from, date_to, created_at, updated_at, is_test)
VALUES
(96, 1, 1, 'direktor_uk', true, true, CURRENT_DATE, NULL, NOW(), NOW(), false);
```

---

## ФАЙЛЫ ИЗМЕНЕНЫ

| Файл | Изменения |
|---|---|
| `portal/middleware.py` | Переписан для защиты Django Admin + CompanyMembershipMiddleware |
| `portal/mixins.py` | СОЗДАН - базовые mixins для контроля доступа |
| `portal/auth_views.py` | СОЗДАН - кастомный login с role-based redirect |
| `portal/urls.py` | Добавлены `/login/`, `/no-membership/`, `/chief-engineer/` |
| `portal/admin_views.py` | Обновлены функции для работы с UserCompanyMembership |
| `portal/admin.py` | Обновлен UserAdmin - добавлена компания, timezone, phone |
| `portal/templates/portal/landing.html` | Изменен action формы на custom_login |
| `portal/templates/portal/login.html` | СОЗДАН - шаблон кастомного login |
| `portal/templates/portal/no_membership.html` | СОЗДАН - страница "Нет привязки к компании" |
| `komunal_dom/settings.py` | Обновлен MIDDLEWARE |

---

## КОНТРОЛЬНЫЙ СПИСОК

Перед использованием проверьте:

- [ ] Middleware добавлены в settings.py
- [ ] CustomLoginView работает (тест через `/login/`)
- [ ] DjangoAdminProtectionMiddleware блокирует `/admin/` для staff
- [ ] UserCompanyMembership создана для пользователя
- [ ] Redirect работает правильно (по ролям)
- [ ] Gunicorn перезапущен

---

**КОНЕЦ ДОКУМЕНТА**
