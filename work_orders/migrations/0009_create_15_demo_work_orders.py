"""
Миграция: Создание 15 демонстрационных заявок

Создает разнообразные тестовые заявки:
- Для 3 разных компаний
- С разными услугами (15 типов)
- В разных статусах (все 8 статусов)
- Для разных исполнителей (12 пользователей)
- С разными приоритетами и аварийностью
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('work_orders', '0008_create_demo_work_orders_and_fill_rules'),
    ]

    operations = [
        migrations.RunSQL(
            """
            -- Заявка 6: Новая, аварийная, критический приоритет (Компания 1, сантехника)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, updated_at, is_test)
            VALUES
            ('DEMO-006', 1, 1, 2, 40, 80, NULL, 'manual_django_admin',
             'Прорыв трубы в подвале', 'Потек воды из стояка, заливает подвал',
             NULL, true, 'critical',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'new_registered'),
             now() - interval '3 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 7: В работе, обычная (Компания 2, электрика, исполнитель smirnov_ap)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-007', 2, 3, 14, 37, 81, 87, 'manual_operator',
             'Перегорели лампы в подъезде', 'На всех этажах перегорели лампы',
             NULL, false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'in_progress'),
             now() - interval '1 day', now() - interval '20 hours', now() - interval '18 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 8: Выполнена (Компания 1, лифт, исполнитель petrov_is)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, completed_by_user_id,
             updated_at, is_test)
            VALUES
            ('DEMO-008', 1, 4, 8, 38, 83, 88, 'manual_django_admin',
             'Лифт не открывается на 3 этаже', 'Лифт застревает между 2 и 3 этажом',
             'Заменены тросы и кнопки, лифт работает нормально', false, 'high',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'completed'),
             now() - interval '3 days', now() - interval '2 days', now() - interval '1 day',
             now() - interval '2 hours', 88, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 9: Приостановлена (Компания 3, газ, исполнитель orlov_pi)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-009', 3, 5, 4, 39, 84, 89, 'manual_django_admin',
             'Запах газа в квартире', 'Пахнет газом на кухне',
             'Ожидание проверки газовой службой', true, 'critical',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'on_hold'),
             now() - interval '5 hours', now() - interval '4 hours', now() - interval '3 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 10: Закрыта (Компания 2, сантехника, исполнитель lebedev_av)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, closed_at,
             completed_by_user_id, closed_by_user_id, updated_at, is_test)
            VALUES
            ('DEMO-010', 2, 6, 1, 36, 80, 90, 'manual_operator',
             'Засор в раковине', 'Вода не уходит из раковины на кухне',
             'Прочистили трубы, вода уходит нормально', false, 'low',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'closed'),
             now() - interval '6 days', now() - interval '5 days', now() - interval '4 days',
             now() - interval '2 days', now() - interval '1 day', 90, 90, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 11: Принята исполнителем (Компания 1, вентиляция, исполнитель frolova_em)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, updated_at, is_test)
            VALUES
            ('DEMO-011', 1, 7, 5, 36, 80, 91, 'manual_employee',
             'Плохая вентиляция в ванной', 'В ванной постоянно сыро и плесень',
             NULL, false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'accepted_by_executor'),
             now() - interval '12 hours', now() - interval '10 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 12: В работе, аварийная (Компания 3, электрика, исполнитель morozov_vp)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-012', 3, 8, 3, 37, 81, 92, 'manual_employee',
             'Выключило свет в подъезде', 'Весь подъезд без электричества',
             NULL, true, 'high',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'in_progress'),
             now() - interval '6 hours', now() - interval '5 hours', now() - interval '4 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 13: Отменена (Компания 2, протечка крыши)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, cancelled_at, cancelled_by_user_id, updated_at, is_test)
            VALUES
            ('DEMO-013', 2, 9, 13, 40, 82, NULL, 'manual_django_admin',
             'Протекает крыша', 'После дождя протекает крыша на 4 этаже',
             'Отмена заявки - дубликат', false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'cancelled'),
             now() - interval '2 days', now() - interval '1 day', 1, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 14: Переоткрыта (Компания 1, конструкция, исполнитель belova_ns)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, closed_at, reopened_at,
             completed_by_user_id, closed_by_user_id, parent_work_order_id,
             updated_at, is_test)
            VALUES
            ('DEMO-014', 1, 10, 7, 36, 80, 93, 'manual_django_admin',
             'Треснула стена в подъезде', 'На лестничной клетке трещина в стене',
             'Работа выполнена некачественно, трещина появилась снова', false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'reopened'),
             now() - interval '10 days', now() - interval '9 days', now() - interval '8 days',
             now() - interval '5 days', now() - interval '3 days', now() - interval '1 day',
             93, 93, (SELECT id FROM request_mgmt.work_order WHERE work_order_no = 'DEMO-003'),
             now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 15: Новая, обычная (Компания 3, пожарная система)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, updated_at, is_test)
            VALUES
            ('DEMO-015', 3, 1, 6, 37, 81, NULL, 'manual_django_admin',
             'Не работает пожарная сигнализация', 'Сигнализация молчит',
             NULL, false, 'high',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'new_registered'),
             now() - interval '1 hour', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 16: В работе (Компания 2, лифт, исполнитель resident1 - житель)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-016', 2, 2, 8, 38, 83, 94, 'manual_django_admin',
             'Лифт дребезжит при движении', 'Лифт сильно дребезжит и стучит',
             NULL, false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'in_progress'),
             now() - interval '2 days', now() - interval '1 day', now() - interval '20 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 17: Выполнена, аварийная (Компания 1, газ, исполнитель resident2)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, completed_by_user_id,
             updated_at, is_test)
            VALUES
            ('DEMO-017', 1, 3, 15, 39, 84, 95, 'manual_employee',
             'Проверка газового оборудования', 'Плановая проверка газа',
             'Проверено, утечек нет, оборудование в норме', true, 'critical',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'completed'),
             now() - interval '4 days', now() - interval '3 days', now() - interval '2 days',
             now() - interval '1 day', 95, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 18: Новая, низкий приоритет (Компания 3, sanitation)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, updated_at, is_test)
            VALUES
            ('DEMO-018', 3, 4, 11, 36, 80, NULL, 'manual_operator',
             'Мусор в подъезде', 'Нужно убрать мусор из подъезда',
             NULL, false, 'low',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'new_registered'),
             now() - interval '30 minutes', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 19: Закрыта (Компания 2, авария коммуникаций, исполнитель ivanov_sv)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, completed_at, closed_at,
             completed_by_user_id, closed_by_user_id, updated_at, is_test)
            VALUES
            ('DEMO-019', 2, 5, 13, 40, 82, 86, 'manual_operator',
             'Разбита труба водоснабжения', 'На улице разбита труба, течет вода',
             'Заменен участок трубы, вода восстановлена', true, 'high',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'closed'),
             now() - interval '8 days', now() - interval '7 days', now() - interval '6 days',
             now() - interval '3 days', now() - interval '1 day', 86, 86, now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;

            -- Заявка 20: В работе (Компания 1, электроснабжение, исполнитель alex)
            INSERT INTO request_mgmt.work_order
            (work_order_no, company_id, object_id, service_id, route_id, department_id,
             responsible_user_id, creation_source, original_request_text, additional_info_text,
             resolution_text, is_emergency, priority_code, current_internal_status_id,
             created_at, accepted_at, in_progress_at, updated_at, is_test)
            VALUES
            ('DEMO-020', 1, 6, 14, 37, 81, 32, 'manual_django_admin',
             'Мерцает свет в квартире', 'Свет постоянно моргает',
             NULL, false, 'normal',
             (SELECT id FROM request_mgmt.work_order_status_ref WHERE short_code_en = 'in_progress'),
             now() - interval '4 hours', now() - interval '3 hours', now() - interval '2 hours', now(), true)
            ON CONFLICT (work_order_no) DO NOTHING;
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
    ]
