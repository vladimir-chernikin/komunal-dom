# Удаление подсистемы file_manager

Дата: 2026-04-22

Подсистема пользовательских файлов `file_manager` удалена из проекта как неиспользуемая.

Перед удалением проверено:

- модель `file_manager.UserFile`: `0` записей;
- пользователи с файлами: отсутствуют;
- рабочий URL `/files/`: удаляется;
- Django app `file_manager.apps.FileManagerConfig`: удаляется из `INSTALLED_APPS`;
- таблица `file_manager_userfile`: удаляется миграцией `portal.0024_drop_file_manager`;
- записи `django_content_type` и `auth_permission` для `app_label = 'file_manager'`: удаляются этой же миграцией.

Удаленные интерфейсы:

- `/files/`;
- раздел `Файлы` в Django Admin;
- карточка и быстрые ссылки файлового менеджера в портальных админских страницах.

