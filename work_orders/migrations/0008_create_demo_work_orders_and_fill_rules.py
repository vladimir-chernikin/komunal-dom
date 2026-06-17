"""
Миграция: Создание демонстрационных заявок и заполнение правил переходов

1. Заполняет описание и правила переходов для всех статусов
2. Создает переходы статусов
3. Создает демонстрационные заявки для тестирования UI
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0007_remove_external_status_from_work_order'),
    ]

    operations = [
        # Заполняем правила для каждого статуса отдельным SQL
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Новая'' - заявка только что создана и еще не распределена на исполнителя.

ВХОД: из внешних систем (MAX, Telegram), вручную оператором/директором
ВЫХОД: в статусы ''Принята исполнителем'' (требуется назначение исполнителя), ''Отменена''
ОГРАНИЧЕНИЯ:
- Нельзя перейти в ''Выполнена'' или ''Закрыта'' минусы исполнителя
- Можно редактировать все поля заявки
- Можно менять услугу и объект
- Обязательно назначить ответственного исполнителя для дальнейшего движения'
               WHERE short_code_en = 'new_registered';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Принята исполнителем'' - исполнитель назначен и ознакомился с заявкой.

ВХОД: из статуса ''Новая'' (требуется назначение исполнителя)
ВЫХОД: в статусы ''В работе'', ''Приостановлена'', ''Отменена''
ОГРАНИЧЕНИЯ:
- Исполнитель должен быть назначен
- Можно редактировать дополнительные сведения
- Нельзя менять услугу и объект
- Исполнитель может взять в работу или приостановить'
               WHERE short_code_en = 'accepted_by_executor';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''В работе'' - исполнитель активно выполняет работы по заявке.

ВХОД: из статусов ''Принята исполнителем'', ''Переоткрыта''
ВЫХОД: в статусы ''Выполнена'' (обязательно resolution_text + фото результата), ''Приостановлена'', ''Отменена''
ОГРАНИЧЕНИЯ:
- Исполнитель должен быть назначен
- Можно добавлять вложения (фото хода работ)
- Можно редактировать additional_info_text
- Нельзя менять услугу, объект, исполнителя
- Обязательно заполнить resolution_text для перехода в ''Выполнена''
- Требуется фото результата для качественного закрытия'
               WHERE short_code_en = 'in_progress';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Приостановлена'' - работа по заявке временно приостановлена по инициативе исполнителя или руководства.

ВХОД: из статусов ''Принята исполнителем'', ''В работе''
ВЫХОД: в статусы ''В работе'' (продолжить), ''Отменена'' (при невозможности выполнения)
ОГРАНИЧЕНИЯ:
- Требуется комментарий о причине приостановки
- Можно изменить ответственного исполнителя
- Нельзя изменить услугу и объект
- Автоматически уведомляет руководство о приостановке'
               WHERE short_code_en = 'on_hold';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Выполнена'' - работы по заявке завершены, ждет контроля и закрытия.

ВХОД: из статуса ''В работе'' (обязательно resolution_text + фото результата)
ВЫХОД: в статусы ''Закрыта'' (окончательное закрытие), ''Переоткрыта'' (если работа выполнена некачественно)
ОГРАНИЧЕНИЯ:
- ОБЯЗАТЕЛЬНО: заполнен resolution_text с описанием выполненных работ
- РЕКОМЕНДУЕТСЯ: фото результата выполнения
- Нельзя редактировать original_request_text
- Нельзя менять услугу, объект
- Можно добавить дополнительные вложения
- Только исполнитель или руководитель могут закрыть заявку'
               WHERE short_code_en = 'completed';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Закрыта'' - заявка окончательно закрыта, жизненный цикл завершен.

ВХОД: из статусов ''Выполнена'' (контроль качества), ''Отменена''
ВЫХОД: только в статус ''Переоткрыта'' (при рекламации или повторном обращении)
ОГРАНИЧЕНИЯ:
- Терминальный статус - нет дальнейших переходов кроме переоткрытия
- Все поля frozen - нельзя редактировать
- Можно только просматривать историю и вложения
- Автоматически уведомляет жителя о закрытии'
               WHERE short_code_en = 'closed';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Отменена'' - заявка отменена по инициативе ЖКХ, жителя или технической невозможности выполнения.

ВХОД: из любого статуса (разрешено ролями direktor_uk, chief_engineer, django_admin)
ВЫХОД: в статус ''Закрыта'' (окончательное архивирование), ''Переоткрыта'' (если отмена ошибочна)
ОГРАНИЧЕНИЯ:
- Терминальный статус - требует высоких прав для отмены
- ОБЯЗАТЕЛЬНО: указать причину отмены в resolution_text
- Требует подтверждения от директора или главного инженера
- Житель получает уведомление об отмене с причиной'
               WHERE short_code_en = 'cancelled';""",
            reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            """UPDATE request_mgmt.work_order_status_ref
               SET description_and_transition_rules = 'Статус ''Переоткрыта'' - заявка была закрыта/выполнена, но reopened по рекламации или повторному обращению.

ВХОД: из статусов ''Выполнена'', ''Закрыта'', ''Отменена''
ВЫХОД: в статусы ''В работе'' (новое выполнение), ''Отменена'' (если переоткрытие ошибочно)
ОГРАНИЧЕНИЯ:
- ОБЯЗАТЕЛЬНО: указать причину переоткрытия в resolution_text
- Создает связь с родительской заявкой (parent_work_order)
- Сохраняет историю выполнения предыдущего цикла
- Требует назначения исполнителя (можно того же или другого)
- Используется для отслеживания качества выполнения (повторные обращения)'
               WHERE short_code_en = 'reopened';""",
            reverse_sql=migrations.RunSQL.noop
        ),

        # Создаем переходы статусов
        migrations.RunSQL(
            """
            DELETE FROM request_mgmt.work_order_status_transition;

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, NULL, false, false, false, false, false, true,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'new_registered' AND ts.short_code_en = 'accepted_by_executor';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'executor', false, false, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'accepted_by_executor' AND ts.short_code_en = 'in_progress';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'executor', false, true, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'accepted_by_executor' AND ts.short_code_en = 'on_hold';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'executor', false, false, false, true, true, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'in_progress' AND ts.short_code_en = 'completed';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'executor', false, true, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'in_progress' AND ts.short_code_en = 'on_hold';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'executor', false, false, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'on_hold' AND ts.short_code_en = 'in_progress';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'chief_engineer', false, false, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'completed' AND ts.short_code_en = 'closed';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'direktor_uk', false, true, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'completed' AND ts.short_code_en = 'reopened';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'django_admin', false, true, false, false, false, false,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'closed' AND ts.short_code_en = 'reopened';

            INSERT INTO request_mgmt.work_order_status_transition
            (from_status_id, to_status_id, allowed_role_code, is_system_transition, require_comment,
             require_reason_code, require_resolution_text, require_result_photo, require_executor_assigned,
             is_active, created_at, updated_at, is_test)
            SELECT fs.id, ts.id, 'chief_engineer', false, false, false, false, false, true,
                   true, now(), now(), false
            FROM request_mgmt.work_order_status_ref fs
            CROSS JOIN request_mgmt.work_order_status_ref ts
            WHERE fs.short_code_en = 'reopened' AND ts.short_code_en = 'in_progress';
            """,
            reverse_sql=migrations.RunSQL.noop
        ),

        # Создаем демонстрационные заявки
        migrations.RunSQL(
            """
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, updated_at, is_test)
            VALUES
            ('DEMO-001', 1, 1, 1, 36, 80, NULL, 'manual_django_admin',
             'Протекает кран на кухне', 'Кран постоянно капает, мешает спать',
             NULL, false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'new_registered'),
             now(), now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-002', 1, 2, 3, 37, 81, 86, 'manual_django_admin',
             'Заменить лампочку в подъезде', 'На 2 этаже не горит лампочка',
             NULL, false, 'low',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'in_progress'),
             now() - interval '2 days', now() - interval '1 day', now() - interval '1 day', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, updated_at, is_test)
            VALUES
            ('DEMO-003', 1, 1, 1, 36, 80, 86, 'manual_django_admin',
             'Уборка снега у подъезда', 'Сугроб высотой 1 метр',
             'Уборка выполнена, снег вывезен. Площадка чистая.', false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'completed'),
             now() - interval '5 days', now() - interval '4 days', now() - interval '3 days',
             now() - interval '1 day', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-004', 1, 1, 1, 36, 80, 86, 'manual_django_admin',
             'Ремонт двери в подвале', 'Дверь не закрывается, сквозит',
             'Ожидание поставки новой двери', false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'on_hold'),
             now() - interval '3 days', now() - interval '2 days', now() - interval '2 days', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, closed_at,
             completed_by_user_id, closed_by_user_id, updated_at, is_test)
            VALUES
            ('DEMO-005', 1, 2, 3, 37, 81, 86, 'manual_django_admin',
             'Починить розетку в квартире', 'Не работает розетка в спальне',
             'Заменил розетку, все работает', false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'closed'),
             now() - interval '7 days', now() - interval '6 days', now() - interval '5 days',
             now() - interval '2 days', now() - interval '1 day', 86, 86, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
