# Подсистема: Portal shell / административные кабинеты / support UI

Дата: 2026-04-07

## Назначение

Подсистема `portal` не равна одной бизнес-функции.

Она сейчас выполняет несколько ролей одновременно:
- корневая веб-оболочка сайта;
- логин / welcome / landing;
- кабинеты ролей;
- часть административных экранов;
- legacy-маршруты;
- UI-точка входа для нормативного консультанта;
- UI-точка входа для трассировки диалогов.

То есть это не одна bounded context бизнес-подсистема, а текущий orchestration/UI shell слой.

## Основные точки входа

Пруф:
- [portal/urls.py](/var/www/komunal-dom_ru/portal/urls.py)

Главные маршруты:
- `/`
- `/login/`
- `/welcome/`
- `/subscribers/`
- `/regulatory-chat/`
- `/executor/`
- `/contractor/`
- `/chief-engineer/`
- `/director/`
- `/admin-uk/`
- `/admin-uk/prompts/`
- `/admin-uk/kladr/...`
- `/admin-uk/dialog-trace/...`

## Основные файлы

- [portal/urls.py](/var/www/komunal-dom_ru/portal/urls.py)
- [portal/views.py](/var/www/komunal-dom_ru/portal/views.py)
- [portal/admin_views.py](/var/www/komunal-dom_ru/portal/admin_views.py)
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)
- [portal/mixins.py](/var/www/komunal-dom_ru/portal/mixins.py)

## Что реально делает portal

### 1. Оболочка и стартовые экраны

- landing
- welcome
- login/no-membership

### 2. Ролевые кабинеты

- subscriber page
- director page
- chief engineer page
- contractor redirect
- executor alias / legacy surface

### 3. Админский shell для УК

- `/admin-uk/`
- статистика пользователей
- статистика файлов
- статистика промптов
- ссылка на КЛАДР
- ссылка на диалоговую трассировку

### 4. Переходный слой совместимости

- legacy executor routes;
- часть logic alias-ов на новый `work_orders`.

## Таблицы, на которые portal точно опирается

- `portal_userprofile`
- `nsi_company`
- `request_mgmt.user_company_membership`
- `request_mgmt.company_department`
- `request_mgmt.work_order`
- `portal_aiprompt`
- `file_manager_userfile`

Опционально в статистике/экранах:
- `kladr_*`
- `dialog_logs`

## Пруфы по опоре на role/membership слой

### UserProfile

Пруф:
- [portal/models.py](/var/www/komunal-dom_ru/portal/models.py)

Факт:
- `UserProfile` хранит роль и primary company/department.

### Membership и role-based access

Пруфы:
- [portal/mixins.py](/var/www/komunal-dom_ru/portal/mixins.py)
- [portal/admin_views.py](/var/www/komunal-dom_ru/portal/admin_views.py)

Факты:
- новый role/access слой уже проверяется через `UserCompanyMembership`;
- `portal` использует `get_primary_membership(...)`;
- статистика пользователей строится через `UserCompanyMembership`.

Это значит:
- `portal` уже находится в процессе миграции от старого role-подхода к новому membership-подходу.

## Пруфы по опоре на work_orders

Пруф:
- [portal/views.py](/var/www/komunal-dom_ru/portal/views.py)

Факты:
- `subscriber_page()` читает `WorkOrder`;
- `executor_dashboard()` перенаправляет на новый `work_orders` dashboard;
- `contractor_dashboard()` вызывает `ContractorDashboardView` из `work_orders`.

Следствие:
- `portal` в части UI уже является оболочкой над `work_orders`, а не отдельной системой заявок.

## Что в portal лучше считать переходным слоем

- legacy `/executor/...`
- часть старых role-проверок через `UserProfile.role`
- часть prompt/admin экранов
- часть historical business logic в `portal/views.py`

## Что в portal лучше считать постоянной ответственностью

- оболочка сайта;
- маршрутизация по кабинетам;
- entry pages;
- общая навигация;
- тонкий UI-слой над другими подсистемами.

## Риски

1. `portal` слишком широк.
В нем смешаны:
- UI shell;
- legacy заявок;
- нормативный UI;
- трассировка;
- admin-кабинеты;
- куски доменной логики.

2. Role model переходная.
Есть и `UserProfile.role`, и `UserCompanyMembership.role_code`.

3. `portal` легко перепутать с отдельной бизнес-подсистемой, хотя он все больше становится orchestration/UI shell слоем.

## Предварительная целевая ответственность подсистемы

`portal` логично оставить как:
- web shell;
- routing;
- role-based entrypoints;
- UI composition layer.

Из него со временем стоит выносить:
- legacy SQL по заявкам;
- доменную AI-логику;
- тяжелую прикладную админ-логику, если она будет расти.

