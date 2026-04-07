# Task: User primary company/department refactor + global close button style

## Политика интерактивности
Разрешен не более 1 вопроса за весь цикл выполнения.
Этот вопрос допустим только один раз и только если найден реальный архитектурный конфликт, который нельзя безопасно разрешить по коду.
Во всех остальных случаях:
- не спрашивай разрешение на чтение файлов
- не спрашивай разрешение на изменение уже перечисленных файлов
- не спрашивай разрешение на создание миграций
- не спрашивай разрешение на перезапуск/reload
- не спрашивай разрешение на browser verification
- не останавливайся на плане

## ID
2026-04-06-user-company-refactor

## Цель
Сделать в карточке пользователя простой основной сценарий 1-к-1 через поля основной компании и основного подразделения, сохранив существующий механизм множественных привязок через UserCompanyMembership для редких случаев работы пользователя в нескольких компаниях.

## Реальная текущая архитектура проекта
1. Пользователь: стандартный `django.contrib.auth.models.User`
2. Расширенный профиль: `portal.models.UserProfile`
3. Компания: `nsi.models.Company`
4. Подразделение компании: `work_orders.models.CompanyDepartment`
5. Текущая связка пользователя с компанией/подразделением/ролью: `work_orders.models.UserCompanyMembership`
6. Текущий Django admin пользователя: `portal/admin.py`, класс `UserAdmin`
7. Текущая middleware-привязка company/department в request: `portal/middleware.py`, класс `CompanyMembershipMiddleware`
8. Текущие role/filter helper'ы: `portal/mixins.py`
9. Текущий login redirect и membership check: `portal/auth_views.py`
10. Ключевые views с фильтрацией по компании и подразделению: `work_orders/views.py`, `portal/admin_views.py`
11. Глобальный шаблон кнопок форм: `templates/admin/change_form.html`

## Что есть сейчас
1. В `portal/admin.py` компания пользователя выводится readonly-методами `get_company()` и `get_company_link()` из `UserCompanyMembership`.
2. В `UserAdmin.fieldsets` на вкладке `Основная информация` сейчас нет редактируемых полей основной компании и основного подразделения.
3. Основная привязка пользователя сейчас вычисляется через `UserCompanyMembership.is_primary=True`, либо fallback на первую активную запись.
4. `CompanyMembershipMiddleware` кладет в request только одну primary membership:
   - `request.user_company_id`
   - `request.user_department_id`
   - `request.user_role_code`
   - `request.user_primary_membership`
5. `portal.mixins.get_primary_membership()` и несколько views завязаны на единственную primary membership.
6. `work_orders/views.py` местами уже умеет работать с несколькими membership, но во многих местах все равно берет только одну primary/first membership.

## Требуемое изменение структуры
1. Добавить в `User` два новых реквизита бизнес-привязки:
   - `primary_company`
   - `primary_department`
2. Эти поля должны быть доступны в карточке пользователя как основные редактируемые реквизиты на вкладке `Основная информация`.
3. Существующую таблицу `UserCompanyMembership` сохранить.
4. Существующий справочник `UserCompanyMembership` показать внизу вкладки `Основная информация` пользователя как блок множественных привязок.
5. Для 90% кейсов логика должна работать через `primary_company` и `primary_department`.
6. Для редких кейсов, когда у пользователя несколько компаний, логика должна уметь использовать набор активных membership.

## Целевая бизнес-логика
1. Если у пользователя одна активная привязка, система должна корректно работать через `primary_company` и `primary_department`.
2. Если у пользователя несколько активных membership, система должна:
   - хранить `primary_company` и `primary_department` как основной контекст по умолчанию
   - использовать все активные membership там, где нужна фильтрация по нескольким компаниям или подразделениям
3. Правило согласованности:
   - `primary_company` и `primary_department` должны либо совпадать с одной из активных записей `UserCompanyMembership`, либо код должен явно и безопасно синхронизировать это состояние
4. Вход в систему, redirect и middleware не должны ломаться.
5. Фильтрация в интерфейсах директора, главного инженера, исполнителя и в списках заявок должна учитывать новую логику.

## Обязательные файлы для чтения и изменения
1. `portal/admin.py`
2. `portal/models.py`
3. `work_orders/models.py`
4. `portal/middleware.py`
5. `portal/mixins.py`
6. `portal/auth_views.py`
7. `work_orders/views.py`
8. `portal/admin_views.py`
9. `templates/admin/change_form.html`
10. связанные миграции в `portal/migrations/` и/или `work_orders/migrations/`

## Ожидаемое техническое решение
1. Выбрать корректный способ хранения `primary_company` и `primary_department` без ломки `django.contrib.auth.User`.
2. Предпочтительно использовать безопасное расширение через связанную модель, если прямое добавление полей в `auth_user` технически хуже для проекта.
3. В admin пользователя показать эти поля как обычные основные реквизиты, а не как readonly badge.
4. Inline/блок `UserCompanyMembership` встроить в страницу пользователя внизу вкладки `Основная информация`.
5. Обновить middleware и helper'ы так, чтобы в request были доступны:
   - основной company/department контекст
   - при необходимости список доступных company ids и department ids
6. Исправить login redirect и бизнес-фильтрацию в местах, где сейчас используется только одна membership.
7. Глобально сделать белый текст кнопки `Закрыть` во всех формах, использующих `templates/admin/change_form.html`.

## Требования к миграции данных
1. Для каждого пользователя без новых primary-полей определить основную пару company/department из `UserCompanyMembership`.
2. Приоритет выбора:
   - активная запись с `is_primary=True` и `date_to IS NULL`
   - иначе первая активная запись
   - иначе поля остаются пустыми
3. Если новая primary-пара определена, она должна быть согласована с active membership.
4. В финальном отчете обязательно описать реализованное правило миграции.

## Browser verification
После патча обязательно:
1. выполнить `manage.py check`
2. перезапустить/reload приложение при необходимости
3. открыть форму пользователя в браузере
4. сделать скриншот формы с полями основной компании и подразделения
5. сделать скриншот нижнего блока `UserCompanyMembership`
6. сделать скриншот, где видно белый текст кнопки `Закрыть`
7. прогнать сценарий из `tasks/2026-04-06-user-company-refactor/scenario.yaml`
8. сохранить артефакты в `tmp_archive/ui_runs/2026_04_06_user_company_refactor/`

## Definition of Done
См. `acceptance.md`

## Формат финального ответа
Покажи только:
1. измененные файлы
2. созданные миграции
3. правило переноса данных
4. какие места бизнес-логики исправлены
5. результат browser verification
6. пути к скриншотам и `report.json`
7. оставшиеся риски, если они есть
