"""
Management command для создания демонстрационных данных подсистемы управления заявками ЖКХ

Использование:
    python manage.py seed_demo_work_orders --reset

Команда создает:
- 2 компании с оргструктурой
- 3 внешние подрядные организации
- Пользователей-сотрудников и жителей
- Маршруты и маппинги
- Тестовые объекты обслуживания
- SLA-политики
- 20-30 тестовых заявок полного жизненного цикла

Все данные создаются с is_test = true
"""
import os
import sys
import random
from datetime import datetime, timedelta, date
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone

from nsi.models import Company
from portal.models import ServicesCatalog, ServiceObject
from work_orders.models import (
    RouteRef, CompanyDepartment, ContractorOrganization,
    CompanyRouteMapping, UserCompanyMembership,
    CompanyObjectServicePeriod, WorkOrderStatusRef,
    SLAPolicy, WorkOrder, SLAInstance,
    WorkOrderEventLog, WorkOrderAttachment
)


class Command(BaseCommand):
    help = 'Создает демонстрационные данные для подсистемы управления заявками'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            dest='reset',
            help='Удалить все тестовые данные перед созданием (is_test = true)',
        )

    def handle(self, *args, **options):
        reset = options.get('reset', False)

        if reset:
            self.clear_test_data()
            self.stdout.write(self.style.WARNING('Все тестовые данные удалены\n'))

        self.create_demo_data()
        self.stdout.write(self.style.SUCCESS('\n✓ Демонстрационные данные созданы успешно!'))

    def clear_test_data(self):
        """Удаляет все тестовые данные (is_test = true)"""
        self.stdout.write('Удаление тестовых данных...')

        # Удаляем в правильном порядке из-за FK constraints
        WorkOrderAttachment.objects.filter(is_test=True).delete()
        WorkOrderEventLog.objects.filter(is_test=True).delete()
        SLAInstance.objects.filter(is_test=True).delete()
        WorkOrder.objects.filter(is_test=True).delete()

        # Удаляем SLA-политики
        SLAPolicy.objects.filter(is_test=True).delete()

        # Удаляем периоды обслуживания
        CompanyObjectServicePeriod.objects.filter(is_test=True).delete()

        # Удаляем членства
        UserCompanyMembership.objects.filter(is_test=True).delete()

        # Удаляем маппинги маршрутов
        CompanyRouteMapping.objects.filter(is_test=True).delete()

        # Удаляем подразделения
        CompanyDepartment.objects.filter(is_test=True).delete()

        # Удаляем подрядчиков
        ContractorOrganization.objects.filter(is_test=True).delete()

        # Удаляем маршруты
        RouteRef.objects.filter(is_test=True).delete()

        # Удаляем тестовых пользователей
        User.objects.filter(username__in=[
            'ivanov_sv', 'smirnov_ap', 'petrov_is', 'orlov_pi', 'lebedev_av',
            'resident1', 'resident2', 'frolova_em', 'morozov_vp', 'belova_ns'
        ]).delete()

        self.stdout.write('  ✓ Тестовые данные удалены\n')

    def create_demo_data(self):
        """Создает демонстрационные данные"""
        self.stdout.write('Создание демонстрационных данных...\n')

        # Получаем или создаем компании
        company1 = Company.objects.filter(name__icontains='Комфорт').first()
        if not company1:
            company1 = Company.objects.create(
                name='ООО УК Комфорт-Сервис',
                full_name='Общество с Ограниченной Ответственностью Управляющая Компания Комфорт-Сервис',
                domain='komfort.uk',
                phone='+7 (495) 123-45-67',
                is_active=True
            )
            self.stdout.write(f'  ✓ Создана компания 1: {company1.name}\n')

        company2 = Company.objects.filter(name__icontains='Сосновый').first()
        if not company2:
            company2 = Company.objects.create(
                name='ТСЖ Сосновый Двор',
                full_name='Товарищество Собственников Жилья Сосновый Двор',
                domain='sosnovy-dvor.tk',
                phone='+7 (495) 987-65-43',
                is_active=True
            )
            self.stdout.write(f'  ✓ Создана компания 2: {company2.name}\n')

        # Проверяем или создаем объекты обслуживания
        self.create_or_get_service_objects(company1, company2)

        # Создаем внешние подрядные организации
        org_lift = self.get_or_create_contractor('ООО Лифт-Сервис Плюс', '7712345678')
        org_gas = self.get_or_create_contractor('ООО ГазТехКонтроль', '7723456789')
        org_emergency = self.get_or_create_contractor('ООО Аварийная Сеть', '7734567890')

        self.stdout.write('  ✓ Подрядные организации созданы\n')

        # Создаем маршруты
        route_plumbing = self.get_or_create_route('plumbing', 'Сантехника')
        route_electricity = self.get_or_create_route('electricity', 'Электрика')
        route_elevator = self.get_or_create_route('elevator', 'Лифты')
        route_gas = self.get_or_create_route('gas', 'Газ')
        route_emergency = self.get_or_create_route('emergency', 'Аварийная протечка')

        # Создаем оргструктуру для компании 1
        dept1_root = self.get_or_create_department(company1, None, 'Компания', 'root')
        dept1_internal = self.get_or_create_department(company1, dept1_root, 'Внутренние службы', 'internal')
        dept1_plumbing = self.get_or_create_department(company1, dept1_internal, 'Сантехники', 'plumbing')
        dept1_electricity = self.get_or_create_department(company1, dept1_internal, 'Электрики', 'electricity')
        dept1_external = self.get_or_create_department(company1, dept1_root, 'Внешние службы', 'external')
        dept1_elevator = self.get_or_create_department(company1, dept1_external, 'Лифтовая служба', 'elevator')
        dept1_gas = self.get_or_create_department(company1, dept1_external, 'Газовая служба', 'gas')

        # Создаем оргструктуру для компании 2
        dept2_root = self.get_or_create_department(company2, None, 'Компания', 'root')
        dept2_operations = self.get_or_create_department(company2, dept2_root, 'Эксплуатация', 'operations')
        dept2_external = self.get_or_create_department(company2, dept2_root, 'Внешние службы', 'external')
        dept2_elevator = self.get_or_create_department(company2, dept2_external, 'Лифтовая служба', 'elevator')

        self.stdout.write('  ✓ Оргструктура создана\n')

        # Создаем маппинги маршрутов
        self.create_route_mappings(company1, company2, dept1_plumbing, dept1_electricity,
                                  dept1_elevator, dept1_gas, dept2_operations, dept2_elevator,
                                  route_plumbing, route_electricity, route_elevator, route_gas, route_emergency)

        # Создаем пользователей
        dept1_root = CompanyDepartment.objects.get(company=company1, department_code='root')
        dept2_root = CompanyDepartment.objects.get(company=company2, department_code='root')
        self.create_users(company1, company2, dept1_plumbing, dept1_electricity,
                          dept1_elevator, dept1_gas, dept2_operations, dept2_elevator,
                          dept1_root, dept2_root, org_lift, org_gas)

        # Создаем SLA-политики (без дубликатов)
        self.create_sla_policies(company1, company2, route_plumbing, route_electricity)

        # Создаем заявки
        self.create_work_orders(company1, company2, dept1_plumbing, dept1_electricity)

        self.stdout.write('  ✓ Создание заявок завершено\n')

    def get_or_create_contractor(self, name, tax_id):
        """Получает или создает подрядную организацию"""
        org, created = ContractorOrganization.objects.get_or_create(
            contractor_name=name,
            defaults={
                'tax_id': tax_id,
                'phone': f'+7 (495) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}',
                'email': f'info@{name.replace(" ", "").lower()}.ru'.replace('ООО', '').lower(),
                'is_active': True,
                'is_test': True
            }
        )
        return org

    def get_or_create_route(self, code, name):
        """Получает или создает маршрут"""
        route, created = RouteRef.objects.get_or_create(
            route_code=code,
            defaults={
                'route_name': name,
                'description': f'{name} - обслуживание',
                'is_active': True,
                'is_test': True
            }
        )
        return route

    def get_or_create_department(self, company, parent, name, code):
        """Получает или создает подразделение"""
        dept, created = CompanyDepartment.objects.get_or_create(
            company=company,
            parent_department=parent,
            department_name=name,
            defaults={
                'department_code': code,
                'is_active': True,
                'is_test': True
            }
        )
        return dept

    def create_or_get_service_objects(self, company1, company2):
        """Создает тестовые объекты обслуживания если их нет"""
        self.stdout.write('  Проверка объектов обслуживания...')

        count = ServiceObject.objects.count()
        if count == 0:
            # Создаем тестовые объекты
            for i in range(1, 6):
                ServiceObject.objects.create(
                    service_object_id=i,
                    building_id=i,
                    unit_id=random.choice([None, i*10+1, i*10+2, i*10+3]) if i > 2 else None,
                    is_active=True,
                    created_at=timezone.now()
                )
            self.stdout.write(f'    ✓ Создано {i} тестовых объектов\n')
        else:
            self.stdout.write(f'    ✓ Найдено {count} объектов\n')

    def create_route_mappings(self, company1, company2, dept1_plumbing, dept1_electricity,
                              dept1_elevator, dept1_gas, dept2_operations, dept2_elevator,
                              route_plumbing, route_electricity, route_elevator, route_gas, route_emergency):
        """Создает маппинги маршрутов"""
        # Удаляем старые маппинги если есть
        CompanyRouteMapping.objects.filter(is_test=True).delete()

        # Компания 1
        CompanyRouteMapping.objects.create(company=company1, route=route_plumbing, target_department=dept1_plumbing, is_test=True)
        CompanyRouteMapping.objects.create(company=company1, route=route_electricity, target_department=dept1_electricity, is_test=True)
        CompanyRouteMapping.objects.create(company=company1, route=route_elevator, target_department=dept1_elevator, is_test=True)
        CompanyRouteMapping.objects.create(company=company1, route=route_gas, target_department=dept1_gas, is_test=True)
        CompanyRouteMapping.objects.create(company=company1, route=route_emergency, target_department=dept1_plumbing, is_test=True)

        # Компания 2
        CompanyRouteMapping.objects.create(company=company2, route=route_plumbing, target_department=dept2_operations, is_test=True)
        CompanyRouteMapping.objects.create(company=company2, route=route_elevator, target_department=dept2_elevator, is_test=True)

        # Дополнительные маппинги для аварий
        CompanyRouteMapping.objects.create(company=company2, route=route_emergency, target_department=dept2_operations, is_test=True)

    def create_users(self, company1, company2, dept1_plumbing, dept1_electricity,
                     dept1_elevator, dept1_gas, dept2_operations, dept2_elevator,
                     dept1_root, dept2_root, org_lift, org_gas):
        """Создает пользователей-сотрудников и жителей"""
        self.stdout.write('  Создание пользователей...\n')

        # Директор компании 1
        director1, _ = User.objects.get_or_create(
            username='ivanov_sv',
            defaults={
                'email': 'ivanov@komfort.uk',
                'first_name': 'Сергей',
                'last_name': 'Иванов',
            }
        )
        director1.set_password('1')
        director1.save()

        UserCompanyMembership.objects.get_or_create(
            user=director1,
            company=company1,
            department=CompanyDepartment.objects.get(company=company1, department_code='root'),
            role_code='direktor_uk',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Главный инженер компании 1
        chief1, _ = User.objects.get_or_create(
            username='smirnov_ap',
            defaults={
                'email': 'smirnov@komfort.uk',
                'first_name': 'Андрей',
                'last_name': 'Смирнов',
            }
        )
        chief1.set_password('1')
        chief1.save()

        dept1_internal = CompanyDepartment.objects.get(company=company1, department_code='internal')
        UserCompanyMembership.objects.get_or_create(
            user=chief1,
            company=company1,
            department=dept1_internal,
            role_code='chief_engineer',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Сантехник компании 1
        plumber1, _ = User.objects.get_or_create(
            username='petrov_is',
            defaults={
                'email': 'petrov@komfort.uk',
                'first_name': 'Иван',
                'last_name': 'Петров',
            }
        )
        plumber1.set_password('1')
        plumber1.save()

        UserCompanyMembership.objects.get_or_create(
            user=plumber1,
            company=company1,
            department=dept1_plumbing,
            role_code='executor',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Электрик компании 1
        electrician1, _ = User.objects.get_or_create(
            username='orlov_pi',
            defaults={
                'email': 'orlov@komfort.uk',
                'first_name': 'Павел',
                'last_name': 'Орлов',
            }
        )
        electrician1.set_password('1')
        electrician1.save()

        UserCompanyMembership.objects.get_or_create(
            user=electrician1,
            company=company1,
            department=dept1_electricity,
            role_code='executor',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Подрядчик-лифтчик (работает на обе компании)
        lift_contractor, _ = User.objects.get_or_create(
            username='lebedev_av',
            defaults={
                'email': 'lebedev@lift-servis.ru',
                'first_name': 'Алексей',
                'last_name': 'Лебедев',
            }
        )
        lift_contractor.set_password('1')
        lift_contractor.save()

        UserCompanyMembership.objects.get_or_create(
            user=lift_contractor,
            company=company1,
            department=dept1_elevator,
            role_code='contractor',
            defaults={
                'contractor_organization': org_lift,
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        UserCompanyMembership.objects.get_or_create(
            user=lift_contractor,
            company=company2,
            department=dept2_elevator,
            role_code='contractor',
            defaults={
                'contractor_organization': org_lift,
                'is_primary': False,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Директор компании 2
        director2, _ = User.objects.get_or_create(
            username='frolova_em',
            defaults={
                'email': 'frolova@sosnovy-dvor.tk',
                'first_name': 'Елена',
                'last_name': 'Фролова',
            }
        )
        director2.set_password('1')
        director2.save()

        UserCompanyMembership.objects.get_or_create(
            user=director2,
            company=company2,
            department=dept2_root,
            role_code='direktor_uk',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Главный инженер компании 2 (он же выполняет заявки)
        chief2, _ = User.objects.get_or_create(
            username='morozov_vp',
            defaults={
                'email': 'morozov@sosnovy-dvor.tk',
                'first_name': 'Виктор',
                'last_name': 'Морозов',
            }
        )
        chief2.set_password('1')
        chief2.save()

        UserCompanyMembership.objects.get_or_create(
            user=chief2,
            company=company2,
            department=dept2_operations,
            role_code='chief_engineer',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Оператор компании 2
        operator2, _ = User.objects.get_or_create(
            username='belova_ns',
            defaults={
                'email': 'belova@sosnovy-dvor.tk',
                'first_name': 'Наталья',
                'last_name': 'Белова',
            }
        )
        operator2.set_password('1')
        operator2.save()

        UserCompanyMembership.objects.get_or_create(
            user=operator2,
            company=company2,
            department=dept2_root,
            role_code='uk_user',
            defaults={
                'is_primary': True,
                'date_from': date.today(),
                'is_active': True,
                'is_test': True
            }
        )

        # Жители
        resident1, _ = User.objects.get_or_create(
            username='resident1',
            defaults={
                'email': 'resident1@example.com',
                'first_name': 'Анна',
                'last_name': 'Сидорова',
            }
        )
        resident1.set_password('1')
        resident1.save()

        resident2, _ = User.objects.get_or_create(
            username='resident2',
            defaults={
                'email': 'resident2@example.com',
                'first_name': 'Михаил',
                'last_name': 'Иванов',
            }
        )
        resident2.set_password('1')
        resident2.save()

        self.stdout.write('    ✓ Пользователи созданы\n')

    def create_sla_policies(self, company1, company2, route_plumbing, route_electricity):
        """Создает SLA-политики без дубликатов"""
        self.stdout.write('  Создание SLA-политик...\n')

        # Очищаем старые тестовые SLA-политики
        SLAPolicy.objects.filter(is_test=True).delete()

        # Получаем услуги
        services = list(ServicesCatalog.objects.filter(is_active=True)[:5])

        if not services:
            self.stdout.write(self.style.WARNING('    ⚠ Услуги не найдены, пропускаем создание SLA-политик\n'))
            return

        created_count = 0
        for service in services:
            for priority in ['low', 'normal', 'high']:
                for is_emergency in [False, True]:
                    try:
                        SLAPolicy.objects.create(
                            company=company1,
                            service=service,
                            is_emergency=is_emergency,
                            priority_code=priority,
                            calendar_type='24x7',
                            executor_assignment_minutes=30 if is_emergency else 60,
                            work_start_minutes=60 if is_emergency else 240,
                            resident_contact_minutes=1440,
                            localization_minutes=120 if is_emergency else None,
                            resolution_minutes=480 if is_emergency else 1440,
                            auto_close_after_days=7,
                            policy_source='company',
                            is_active=True,
                            is_test=True
                        )
                        created_count += 1
                    except:
                        pass  # Пропускаем если дубликат

        self.stdout.write(f'    ✓ Создано {created_count} SLA-политик\n')

    def create_work_orders(self, company1, company2, dept1_plumbing, dept1_electricity):
        """Создает тестовые заявки"""
        self.stdout.write('  Создание заявок...\n')

        # Получаем статусы
        status_new = WorkOrderStatusRef.objects.get(short_code_en='new_registered')
        status_assigned = WorkOrderStatusRef.objects.get(short_code_en='accepted_by_executor')
        status_in_progress = WorkOrderStatusRef.objects.get(short_code_en='in_progress')
        status_completed = WorkOrderStatusRef.objects.get(short_code_en='completed')
        status_closed = WorkOrderStatusRef.objects.get(short_code_en='closed')
        status_on_hold = WorkOrderStatusRef.objects.get(short_code_en='on_hold')

        # Получаем услуги
        services = list(ServicesCatalog.objects.filter(is_active=True)[:10])

        # Получаем объекты
        objects = list(ServiceObject.objects.all()[:5])

        if not objects:
            self.stdout.write(self.style.WARNING('    ⚠ Объекты обслуживания не найдены, пропускаем создание заявок\n'))
            return

        # Получаем пользователей
        plumbers = User.objects.filter(
            company_memberships__department=dept1_plumbing,
            company_memberships__role_code='executor'
        )

        # Создаем 20 заявок
        for i in range(20):
            service = random.choice(services)
            obj = random.choice(objects)

            # Определяем маршрут и подразделение
            mapping = CompanyRouteMapping.objects.filter(
                company=company1,
                is_active=True
            ).first()

            if not mapping:
                continue

            # Определяем статус
            status_options = [status_new, status_in_progress, status_on_hold, status_completed, status_closed]
            if i < 15:
                status = status_options[i % len(status_options)]
            else:
                status = status_completed

            # Генерируем номер заявки
            work_order_no = f'WO-{timezone.now().strftime("%Y%m%d")}-{i+1:03d}'


            # Создаем заявку
            work_order = WorkOrder.objects.create(
                work_order_no=work_order_no,
                company=company1,
                object=obj,
                service=service,
                route=mapping.route,
                department=mapping.target_department,
                creation_source='manual_employee',
                original_request_text=self.get_random_request_text(),
                is_emergency=i % 6 == 0,  # Каждая 6-я заявка аварийная
                priority_code=random.choice(['low', 'normal', 'high']) if not (i % 6 == 0) else 'high',
                current_internal_status=status,
                current_external_status=WorkOrderStatusRef.objects.get(short_code_en='accepted'),
                created_at=timezone.now() - timedelta(hours=random.randint(1, 48)),
                is_test=True
            )

            # Получаем SLA-политику
            sla_policy = SLAPolicy.objects.filter(
                company=company1,
                service=service,
                is_emergency=work_order.is_emergency,
                priority_code=work_order.priority_code,
                is_active=True
            ).first()

            if sla_policy:
                now = work_order.created_at
                SLAInstance.objects.create(
                    work_order=work_order,
                    company=company1,
                    sla_policy=sla_policy,
                    calendar_type=sla_policy.calendar_type,
                    executor_assignment_due_at=now + timedelta(minutes=sla_policy.executor_assignment_minutes),
                    work_start_due_at=now + timedelta(minutes=sla_policy.work_start_minutes),
                    resident_contact_due_at=now + timedelta(minutes=sla_policy.resident_contact_minutes),
                    localization_due_at=now + timedelta(minutes=sla_policy.localization_minutes) if sla_policy.localization_minutes else None,
                    resolution_due_at=now + timedelta(minutes=sla_policy.resolution_minutes),
                    auto_close_due_at=now + timedelta(days=sla_policy.auto_close_after_days) if work_order.current_internal_status == status_completed else None,
                    is_test=True
                )

            # Создаем событие создания
            WorkOrderEventLog.objects.create(
                work_order=work_order,
                company=company1,
                department=work_order.department,
                event_type_code='created',
                event_datetime=work_order.created_at,
                text_value=f'Заявка зарегистрирована: {work_order.original_request_text[:100]}...',
                is_visible_to_resident=False,
                is_test=True
            )

            # Часть заявок в работе
            if status in [status_in_progress, status_on_hold] and plumbers.exists():
                plumber = plumbers.first()
                work_order.responsible_user = plumber
                work_order.assigned_at = timezone.now() - timedelta(hours=random.randint(1, 24))
                work_order.accepted_at = timezone.now() - timedelta(hours=random.randint(1, 12))

                if status == status_in_progress:
                    work_order.in_progress_at = timezone.now() - timedelta(hours=random.randint(1, 6))

                work_order.save()

                # Событие назначения
                WorkOrderEventLog.objects.create(
                    work_order=work_order,
                    company=company1,
                    department=work_order.department,
                    event_type_code='assigned',
                    event_datetime=work_order.assigned_at,
                    text_value=f'Назначен исполнитель: {plumber.get_full_name()}',
                    new_responsible_user_id=plumber.id,
                    is_visible_to_resident=False,
                    is_test=True
                )

            # Часть заявок выполнена
            elif status == status_completed:
                work_order.resolution_text = self.get_resolution_text(service)
                work_order.completed_at = timezone.now() - timedelta(hours=random.randint(1, 48))
                work_order.save()

                # Событие выполнения
                WorkOrderEventLog.objects.create(
                    work_order=work_order,
                    company=company1,
                    department=work_order.department,
                    event_type_code='completed',
                    event_datetime=work_order.completed_at,
                    text_value='Заявка выполнена',
                    is_visible_to_resident=True,
                    is_test=True
                )

            # Часть заявок закрыта
            if status == status_closed:
                # Сначала закрываем как выполненную (если еще не выполнена)
                if not work_order.completed_at:
                    work_order.resolution_text = self.get_resolution_text(service)
                    work_order.completed_at = timezone.now() - timedelta(hours=random.randint(2, 48))

                    # Событие выполнения
                    WorkOrderEventLog.objects.create(
                        work_order=work_order,
                        company=company1,
                        department=work_order.department,
                        event_type_code='completed',
                        event_datetime=work_order.completed_at,
                        text_value='Заявка выполнена',
                        is_visible_to_resident=True,
                        is_test=True
                    )

                # Потом закрываем
                work_order.closed_at = timezone.now() - timedelta(hours=random.randint(1, 2))
                work_order.save()

                # Событие закрытия
                WorkOrderEventLog.objects.create(
                    work_order=work_order,
                    company=company1,
                    department=work_order.department,
                    event_type_code='closed',
                    event_datetime=work_order.closed_at,
                    text_value='Заявка закрыта',
                    is_visible_to_resident=True,
                    is_test=True
                )

        self.stdout.write(f'    ✓ Создано 20 заявок\n')

    def get_random_request_text(self):
        """Генерирует случайный текст заявки"""
        texts = [
            'Протечка крана на кухне. Вода течет непрерывно, уже залило соседей снизу.',
            'Засор в канализации. Вода не уходит, раковина забилась.',
            'Нет света в подъезде. Уже сутки темнота на лестничной клетке.',
            'Лифт не работает. Застрял между 5 и 6 этажом, не открываются двери.',
            'Запах газа в подъезде. Проверьте пожалуйста, есть ли утечка.',
            'Холодный радиатор в квартире. Батарея ледяная, температура низкая.',
            'Протечка кровли. После дождя в углу квартиры потекло сверху.',
            'Сломана входная дверь в подъезд. Дверь не закрывается, замок не работает.',
            'Не закрывается подвальное помещение. Замок сломан, дверь распахнута.',
            'Нет освещения во дворе. Все фонари не горят уже вторые сутки.',
        ]
        return random.choice(texts)

    def get_resolution_text(self, service):
        """Генерирует текст решения"""
        resolutions = [
            'Устранена протечка. Кран заменен, течение остановлено.',
            'Засор прочищен. Вода уходит свободно.',
            'Восстановлено освещение. Лампочки заменены.',
            'Лифт починен. Дверь открывается.',
            'Газ проверен. Утечек не обнаружено.',
            'Температура нормализована. Радиатор прогрет.',
            'Кровля temporarily sealed. Will be monitored.',
            'Дверь отремонирована. Замок заменен.',
            'Подвальное помещение закрыто. Новый замок установлен.',
            'Освещение двора восстановлено. Все лампочки работают.',
        ]
        return random.choice(resolutions)
