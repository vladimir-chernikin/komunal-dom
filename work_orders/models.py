"""
Модели подсистемы управления заявками ЖКХ

Все таблицы находятся в PostgreSQL schema 'request_mgmt'
PK: bigint с identity/auto increment
Обязательное поле: is_test boolean NOT NULL DEFAULT false
"""
import re

from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db.models import UniqueConstraint, Q, CheckConstraint, F, Max


class CompanyDepartment(models.Model):
    """Иерархический справочник подразделений компании (request_mgmt.company_department)"""

    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='departments',
        verbose_name="Компания"
    )
    parent_department = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        db_column='parent_department_id',
        null=True,
        blank=True,
        related_name='child_departments',
        verbose_name="Родительское подразделение"
    )
    department_name = models.CharField(max_length=150, verbose_name="Название")
    department_code = models.CharField(max_length=50, verbose_name="Код")
    is_external = models.BooleanField(default=False, verbose_name="Внешняя организация")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'company_department'
        verbose_name = "Подразделение компании"
        verbose_name_plural = "Подразделения компаний"
        ordering = ['company', 'parent_department_id', 'department_name', 'id']
        constraints = [
            UniqueConstraint(
                fields=['company', 'department_code'],
                name='uq_company_department_company_code'
            ),
            UniqueConstraint(
                fields=['company', 'parent_department', 'department_name'],
                name='uq_company_department_company_name_parent'
            ),
        ]
        indexes = [
            models.Index(fields=['company'], name='idx_company_department_company'),
            models.Index(fields=['parent_department'], name='idx_company_department_parent'),
            models.Index(fields=['company', 'is_active'], name='idx_company_department_active'),
        ]

    def __str__(self):
        return f"{self.department_name} ({self.company.name})"

    @classmethod
    def generate_department_code(cls, company_id, department_name, exclude_id=None):
        translit_map = {
            ord('\u0430'): 'a', ord('\u0431'): 'b', ord('\u0432'): 'v',
            ord('\u0433'): 'g', ord('\u0434'): 'd', ord('\u0435'): 'e',
            ord('\u0451'): 'e', ord('\u0436'): 'zh', ord('\u0437'): 'z',
            ord('\u0438'): 'i', ord('\u0439'): 'y', ord('\u043a'): 'k',
            ord('\u043b'): 'l', ord('\u043c'): 'm', ord('\u043d'): 'n',
            ord('\u043e'): 'o', ord('\u043f'): 'p', ord('\u0440'): 'r',
            ord('\u0441'): 's', ord('\u0442'): 't', ord('\u0443'): 'u',
            ord('\u0444'): 'f', ord('\u0445'): 'h', ord('\u0446'): 'ts',
            ord('\u0447'): 'ch', ord('\u0448'): 'sh', ord('\u0449'): 'sch',
            ord('\u044a'): '', ord('\u044b'): 'y', ord('\u044c'): '',
            ord('\u044d'): 'e', ord('\u044e'): 'yu', ord('\u044f'): 'ya',
        }
        source = (department_name or '').strip().lower()
        transliterated = source.translate(translit_map)
        base_code = re.sub(r'[^a-z0-9]+', '-', transliterated).strip('-') or 'department'
        base_code = base_code[:50].strip('-') or 'department'

        candidate = base_code
        suffix = 2
        queryset = cls.objects.filter(company_id=company_id)
        if exclude_id:
            queryset = queryset.exclude(pk=exclude_id)

        while queryset.filter(department_code=candidate).exists():
            suffix_text = f'-{suffix}'
            candidate = f'{base_code[:50 - len(suffix_text)].strip("-")}{suffix_text}'
            suffix += 1
        return candidate


class ContractorOrganization(models.Model):
    """Справочник подрядных организаций (request_mgmt.contractor_organization)"""

    contractor_name = models.CharField(max_length=200, verbose_name="Название")
    tax_id = models.CharField(max_length=20, blank=True, null=True, verbose_name="ИНН")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="Телефон")
    email = models.EmailField(max_length=254, blank=True, null=True, verbose_name="Email")
    address = models.TextField(blank=True, null=True, verbose_name="Адрес")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'contractor_organization'
        verbose_name = "Подрядная организация"
        verbose_name_plural = "Подрядные организации"
        ordering = ['contractor_name']
        constraints = [
            UniqueConstraint(
                fields=['tax_id'],
                condition=Q(tax_id__isnull=False),
                name='uq_contractor_organization_tax_id'
            ),
        ]
        indexes = [
            models.Index(fields=['contractor_name'], name='idx_contr_org_name'),
            models.Index(fields=['is_active'], name='idx_contr_org_active'),
        ]

    def __str__(self):
        return self.contractor_name


class CompanyRouteMapping(models.Model):
    """Маршрут услуги в конкретной компании (request_mgmt.company_route_mapping)"""

    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='route_mappings',
        verbose_name="Компания"
    )
    service = models.ForeignKey(
        'portal.ServicesCatalog',
        on_delete=models.PROTECT,
        db_column='service_id',
        null=True,
        blank=True,
        related_name='company_route_mappings',
        verbose_name="Услуга"
    )
    target_department = models.ForeignKey(
        CompanyDepartment,
        on_delete=models.PROTECT,
        db_column='target_department_id',
        related_name='incoming_mappings',
        verbose_name="Целевое подразделение"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'company_route_mapping'
        verbose_name = "Маршрут услуги компании"
        verbose_name_plural = "Маршруты услуг компании"
        ordering = ['company', 'service', 'id']
        constraints = [
            UniqueConstraint(
                fields=['company', 'service'],
                condition=Q(service__isnull=False, is_active=True),
                name='uq_company_service_route_active'
            ),
        ]
        indexes = [
            models.Index(fields=['company'], name='idx_comp_route_map_comp'),
            models.Index(fields=['service'], name='idx_comp_route_map_service'),
            models.Index(fields=['target_department'], name='idx_comp_route_map_dept'),
        ]

    def __str__(self):
        route_title = self.service.scenario_name if self.service_id else "без услуги"
        return f"{self.company.name} → {route_title} → {self.target_department.department_name}"


class UserCompanyMembership(models.Model):
    """Привязка пользователя к компании, подразделению и роли (request_mgmt.user_company_membership)"""

    ROLE_CHOICES = [
        ('resident', 'Житель'),
        ('uk_user', 'Пользователь УК'),
        ('executor', 'Исполнитель'),
        ('chief_engineer', 'Главный инженер'),
        ('direktor_uk', 'Директор УК'),
        ('contractor', 'Подрядчик'),
        ('django_admin', 'Django администратор'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='company_memberships',
        verbose_name="Пользователь"
    )
    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.CASCADE,
        db_column='company_id',
        related_name='user_memberships',
        verbose_name="Компания"
    )
    department = models.ForeignKey(
        CompanyDepartment,
        on_delete=models.PROTECT,
        db_column='department_id',
        related_name='user_memberships',
        verbose_name="Подразделение"
    )
    role_code = models.CharField(max_length=50, choices=ROLE_CHOICES, verbose_name="Роль")
    contractor_organization = models.ForeignKey(
        ContractorOrganization,
        on_delete=models.SET_NULL,
        db_column='contractor_organization_id',
        null=True,
        blank=True,
        related_name='user_memberships',
        verbose_name="Подрядная организация"
    )
    is_primary = models.BooleanField(default=False, verbose_name="Основная привязка")
    date_from = models.DateField(verbose_name="Действует с")
    date_to = models.DateField(blank=True, null=True, verbose_name="Действует до")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'user_company_membership'
        verbose_name = "Членство в компании"
        verbose_name_plural = "Членства в компаниях"
        ordering = ['user', 'company', '-is_primary', '-is_active']
        constraints = [
            UniqueConstraint(
                fields=['user', 'company', 'department', 'role_code', 'date_from'],
                name='uq_user_company_membership_identity'
            ),
            UniqueConstraint(
                fields=['user'],
                condition=Q(is_primary=True, is_active=True, date_to__isnull=True),
                name='uq_user_company_membership_primary_active'
            ),
            CheckConstraint(
                condition=Q(date_to__isnull=True) | Q(date_to__gte=F('date_from')),
                name='ck_user_company_membership_date_range'
            ),
        ]
        indexes = [
            models.Index(fields=['user'], name='idx_user_comp_member_user'),
            models.Index(fields=['company'], name='idx_user_comp_member_comp'),
            models.Index(fields=['department'], name='idx_user_comp_member_dept'),
            models.Index(fields=['role_code'], name='idx_user_comp_member_role'),
            models.Index(fields=['user', 'is_active'], name='idx_user_comp_member_active'),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.company.name} ({self.get_role_code_display()})"


class WorkOrderStatusRef(models.Model):
    """Справочник статусов заявки (request_mgmt.work_order_status_ref)"""

    short_code_en = models.CharField(max_length=50, unique=True, verbose_name="Код статуса")
    short_name_ru = models.CharField(max_length=100, verbose_name="Название")
    display_name_for_user = models.CharField(max_length=100, blank=True, null=True, verbose_name="Для пользователя")
    description_and_transition_rules = models.TextField(
        blank=True, null=True, verbose_name="Описание и правила переходов"
    )
    sort_order = models.IntegerField(default=100, verbose_name="Порядок сортировки")
    is_terminal = models.BooleanField(default=False, verbose_name="Конечный статус")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'work_order_status_ref'
        verbose_name = "Статус заявки"
        verbose_name_plural = "Статусы заявок"
        ordering = ['sort_order', 'short_code_en']
        indexes = [
            models.Index(fields=['is_active'], name='idx_work_status_ref_active'),
            models.Index(fields=['sort_order'], name='idx_work_status_ref_sort'),
        ]

    def __str__(self):
        return f"{self.short_name_ru} ({self.short_code_en})"


class SLAPolicy(models.Model):
    """SLA-политики (request_mgmt.sla_policy)"""

    CALENDAR_TYPE_CHOICES = [
        ('24x7', '24/7'),
        ('company_working_hours', 'Рабочие часы компании'),
    ]

    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='sla_policies',
        verbose_name="Компания"
    )
    service = models.ForeignKey(
        'portal.ServicesCatalog',
        on_delete=models.PROTECT,
        db_column='service_id',
        related_name='sla_policies',
        verbose_name="Услуга"
    )
    calendar_type = models.CharField(max_length=25, choices=CALENDAR_TYPE_CHOICES, default='24x7', verbose_name="Тип календаря")
    reaction_minutes = models.IntegerField(
        validators=[MinValueValidator(0)], verbose_name="SLA реакции (мин)"
    )
    localization_minutes = models.IntegerField(
        validators=[MinValueValidator(0)], verbose_name="SLA локализации (мин)"
    )
    completion_minutes = models.IntegerField(
        validators=[MinValueValidator(0)], verbose_name="SLA выполнения (мин)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'sla_policy'
        verbose_name = "SLA-политика"
        verbose_name_plural = "SLA-политики"
        ordering = ['company', 'service']
        constraints = [
            UniqueConstraint(
                fields=['company', 'service', 'is_active'],
                name='uq_sla_policy_company_service_active'
            ),
            CheckConstraint(
                condition=Q(calendar_type__in=['24x7', 'company_working_hours']),
                name='ck_sla_policy_calendar_type'
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'service'], name='idx_sla_policy_company_service'),
            models.Index(fields=['company', 'is_active'], name='idx_sla_policy_active'),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.service.scenario_name}"


class CompanyObjectServicePeriod(models.Model):
    """Период обслуживания объекта компанией (request_mgmt.company_object_service_period)"""

    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='service_periods',
        verbose_name="Компания"
    )
    object = models.ForeignKey(
        'portal.ServiceObject',
        on_delete=models.PROTECT,
        db_column='object_id',
        related_name='service_periods',
        verbose_name="Объект обслуживания"
    )
    date_from = models.DateField(verbose_name="Обслуживание с")
    date_to = models.DateField(blank=True, null=True, verbose_name="Обслуживание по")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'company_object_service_period'
        verbose_name = "Период обслуживания объекта"
        verbose_name_plural = "Периоды обслуживания объектов"
        ordering = ['object', '-date_from']
        constraints = [
            CheckConstraint(
                condition=Q(date_to__isnull=True) | Q(date_to__gte=F('date_from')),
                name='ck_company_object_service_period_date_range'
            ),
            UniqueConstraint(
                fields=['object'],
                condition=Q(is_active=True, is_test=False, date_to__isnull=True),
                name='uq_comp_obj_period_open_live'
            ),
            # Exclusion constraint будет добавлен через миграцию
        ]
        indexes = [
            models.Index(fields=['company'], name='idx_comp_obj_period_comp'),
            models.Index(fields=['object'], name='idx_comp_obj_period_obj'),
            models.Index(fields=['date_from', 'date_to'], name='idx_comp_obj_period_dates'),
        ]

    def __str__(self):
        date_to_str = f" - {self.date_to}" if self.date_to else " (настоящее время)"
        return f"{self.object} - {self.company.name}: {self.date_from}{date_to_str}"


# ============================================
# Документы
# ============================================

class WorkOrder(models.Model):
    """Главная сущность заявки (request_mgmt.work_order)"""

    CREATION_SOURCE_CHOICES = [
        ('bot_json', 'Бот (JSON)'),
        ('manual_operator', 'Вручную оператором'),
        ('manual_employee', 'Вручную сотрудником'),
        ('manual_chief_engineer', 'Вручную главным инженером'),
        ('manual_director', 'Вручную директором'),
        ('manual_django_admin', 'Вручную Django-админом'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Низкий'),
        ('normal', 'Обычный'),
        ('high', 'Высокий'),
        ('critical', 'Критический'),
    ]

    work_order_no = models.CharField(max_length=30, unique=True, verbose_name="Номер заявки")
    company_sequence_no = models.PositiveIntegerField(editable=False, verbose_name="Порядковый номер внутри компании")
    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='work_orders',
        verbose_name="Компания"
    )
    object = models.ForeignKey(
        'portal.ServiceObject',
        on_delete=models.PROTECT,
        db_column='object_id',
        related_name='work_orders',
        verbose_name="Объект обслуживания"
    )
    service = models.ForeignKey(
        'portal.ServicesCatalog',
        on_delete=models.PROTECT,
        db_column='service_id',
        related_name='work_orders',
        verbose_name="Услуга"
    )
    department = models.ForeignKey(
        CompanyDepartment,
        on_delete=models.PROTECT,
        db_column='department_id',
        related_name='work_orders',
        verbose_name="Подразделение"
    )
    responsible_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='responsible_user_id',
        null=True,
        blank=True,
        related_name='assigned_work_orders',
        verbose_name="Ответственный исполнитель"
    )
    message_log_ref = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ссылка на MessageLog")
    creation_source = models.CharField(max_length=30, choices=CREATION_SOURCE_CHOICES, verbose_name="Источник создания")
    resident_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='resident_user_id',
        null=True,
        blank=True,
        related_name='resident_work_orders',
        verbose_name="Авторизованный житель"
    )
    original_request_text = models.TextField(verbose_name="Исходный текст обращения")
    additional_info_text = models.TextField(blank=True, null=True, verbose_name="Дополнительные сведения")
    resolution_text = models.TextField(blank=True, null=True, verbose_name="Решение")
    is_emergency = models.BooleanField(default=False, verbose_name="Аварийная заявка")
    priority_code = models.CharField(max_length=20, choices=PRIORITY_CHOICES, verbose_name="Приоритет")
    current_internal_status = models.ForeignKey(
        WorkOrderStatusRef,
        on_delete=models.PROTECT,
        db_column='current_internal_status_id',
        related_name='status_work_orders',
        verbose_name="Текущий статус"
    )
    parent_work_order = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        db_column='parent_work_order_id',
        null=True,
        blank=True,
        related_name='child_work_orders',
        verbose_name="Родительская заявка"
    )

    # Дата создания
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'work_order'
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ['-created_at']
        constraints = [
            UniqueConstraint(
                fields=['company', 'company_sequence_no'],
                name='uq_work_order_company_sequence_no'
            ),
            CheckConstraint(
                condition=Q(parent_work_order__isnull=True) | ~Q(parent_work_order=F('id')),
                name='ck_work_order_no_self_parent'
            ),
            CheckConstraint(
                condition=Q(creation_source__in=[
                    'bot_json', 'manual_operator', 'manual_employee',
                    'manual_chief_engineer', 'manual_director', 'manual_django_admin'
                ]),
                name='ck_work_order_creation_source'
            ),
            CheckConstraint(
                condition=Q(priority_code__in=['low', 'normal', 'high', 'critical']),
                name='ck_work_order_priority'
            ),
        ]
        indexes = [
            models.Index(fields=['company', '-created_at'], name='idx_work_order_comp_created'),
            models.Index(fields=['company', 'department', 'current_internal_status', '-created_at'], name='idx_work_order_comp_dept_stat'),
            models.Index(fields=['responsible_user', 'current_internal_status', '-created_at'], name='idx_work_order_resp_stat'),
            models.Index(fields=['department', '-created_at'], name='idx_work_order_dept_unassign', condition=Q(responsible_user__isnull=True)),
            models.Index(fields=['parent_work_order'], name='idx_work_order_parent'),
            models.Index(fields=['object'], name='idx_work_order_object'),
            models.Index(fields=['service'], name='idx_work_order_service'),
            models.Index(fields=['is_test'], name='idx_work_order_test'),
        ]

    def __str__(self):
        return f"Заявка #{self.work_order_no}: {self.original_request_text[:50]}..."

    @staticmethod
    def format_work_order_no(company_id, company_sequence_no):
        return f"{company_id}-{company_sequence_no}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.company_id and not self.company_sequence_no:
            with transaction.atomic():
                last_sequence = (
                    WorkOrder.objects.select_for_update()
                    .filter(company_id=self.company_id)
                    .aggregate(max_seq=Max('company_sequence_no'))
                    .get('max_seq')
                    or 0
                )
                self.company_sequence_no = last_sequence + 1
                self.work_order_no = self.format_work_order_no(self.company_id, self.company_sequence_no)
                return super().save(*args, **kwargs)

        if self.company_id and self.company_sequence_no and not self.work_order_no:
            self.work_order_no = self.format_work_order_no(self.company_id, self.company_sequence_no)

        return super().save(*args, **kwargs)


class WorkOrderStatusHistory(models.Model):
    """История изменения статусов заявки (request_mgmt.work_order_status_history)"""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        db_column='work_order_id',
        related_name='status_history',
        verbose_name="Заявка"
    )
    status = models.ForeignKey(
        WorkOrderStatusRef,
        on_delete=models.PROTECT,
        db_column='status_id',
        related_name='history_entries',
        verbose_name="Статус"
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='changed_by_id',
        null=True,
        blank=True,
        related_name='status_changes',
        verbose_name="Пользователь"
    )
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата-Время")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'work_order_status_history'
        verbose_name = "История изменения статуса"
        verbose_name_plural = "Истории изменения статусов"
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['work_order', '-changed_at'], name='idx_status_hist_work_time'),
            models.Index(fields=['status'], name='idx_status_hist_status'),
            models.Index(fields=['changed_by'], name='idx_status_hist_user'),
        ]

    def __str__(self):
        user_str = self.changed_by.get_full_name() if self.changed_by else 'Система'
        return f"{self.work_order.work_order_no} → {self.status.short_name_ru} ({self.changed_at.strftime('%d.%m.%Y %H:%M')})"


class SLAInstance(models.Model):
    """Экземпляр SLA для заявки (request_mgmt.sla_instance)"""

    SLA_STATE_CHOICES = [
        ('waiting', 'Ожидает'),
        ('met', 'Выполнен'),
        ('overdue', 'Просрочен'),
        ('not_applicable', 'Неприменимо'),
    ]

    CALENDAR_TYPE_CHOICES = [
        ('24x7', '24/7'),
        ('company_working_hours', 'Рабочие часы компании'),
    ]

    work_order = models.OneToOneField(
        WorkOrder,
        on_delete=models.CASCADE,
        db_column='work_order_id',
        related_name='sla_instance',
        verbose_name="Заявка"
    )
    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='sla_instances',
        verbose_name="Компания"
    )
    sla_policy = models.ForeignKey(
        SLAPolicy,
        on_delete=models.PROTECT,
        db_column='sla_policy_id',
        related_name='sla_instances',
        verbose_name="SLA-политика"
    )
    calendar_type = models.CharField(max_length=25, choices=CALENDAR_TYPE_CHOICES, verbose_name="Тип календаря")

    reaction_due_at = models.DateTimeField(blank=True, null=True, verbose_name="Дедлайн SLA реакции")
    reaction_stopped_at = models.DateTimeField(blank=True, null=True, verbose_name="Остановлен")
    reaction_state = models.CharField(
        max_length=20, choices=SLA_STATE_CHOICES, default='waiting', verbose_name="Состояние"
    )

    # Таймер локализации аварии
    localization_due_at = models.DateTimeField(blank=True, null=True, verbose_name="Дедлайн локализации")
    localization_stopped_at = models.DateTimeField(blank=True, null=True, verbose_name="Остановлен")
    localization_state = models.CharField(
        max_length=20, choices=SLA_STATE_CHOICES, default='not_applicable', verbose_name="Состояние"
    )

    completion_due_at = models.DateTimeField(blank=True, null=True, verbose_name="Дедлайн SLA выполнения")
    completion_stopped_at = models.DateTimeField(blank=True, null=True, verbose_name="Остановлен")
    completion_state = models.CharField(
        max_length=20, choices=SLA_STATE_CHOICES, default='waiting', verbose_name="Состояние"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'sla_instance'
        verbose_name = "SLA экземпляр"
        verbose_name_plural = "SLA экземпляры"
        ordering = ['-created_at']
        constraints = [
            CheckConstraint(
                condition=Q(calendar_type__in=['24x7', 'company_working_hours']),
                name='ck_sla_instance_calendar_type'
            ),
        ]
        indexes = [
            models.Index(fields=['company'], name='idx_sla_instance_company'),
            models.Index(
                fields=['reaction_due_at'],
                name='idx_sla_inst_reaction_wait',
                condition=Q(reaction_state='waiting')
            ),
            models.Index(
                fields=['localization_due_at'],
                name='idx_sla_inst_local_wait',
                condition=Q(localization_state='waiting')
            ),
            models.Index(
                fields=['completion_due_at'],
                name='idx_sla_inst_completion_wait',
                condition=Q(completion_state='waiting')
            ),
        ]

    def __str__(self):
        return f"SLA для заявки #{self.work_order.work_order_no}"


class WorkOrderEventLog(models.Model):
    """Журнал событий заявки (request_mgmt.work_order_event_log)"""

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        db_column='work_order_id',
        related_name='event_logs',
        verbose_name="Заявка"
    )
    company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.PROTECT,
        db_column='company_id',
        related_name='work_order_event_logs',
        verbose_name="Компания"
    )
    department = models.ForeignKey(
        CompanyDepartment,
        on_delete=models.SET_NULL,
        db_column='department_id',
        null=True,
        blank=True,
        related_name='work_order_event_logs',
        verbose_name="Подразделение"
    )
    event_type_code = models.CharField(max_length=50, verbose_name="Тип события")
    event_datetime = models.DateTimeField(verbose_name="Дата/время события")
    author_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='author_user_id',
        null=True,
        blank=True,
        related_name='created_work_order_events',
        verbose_name="Автор"
    )
    text_value = models.TextField(blank=True, null=True, verbose_name="Текст события")
    event_payload_json = models.JSONField(blank=True, null=True, verbose_name="Дополнительная нагрузка")
    old_status = models.ForeignKey(
        WorkOrderStatusRef,
        on_delete=models.SET_NULL,
        db_column='old_status_id',
        null=True,
        blank=True,
        related_name='old_status_events',
        verbose_name="Старый статус"
    )
    new_status = models.ForeignKey(
        WorkOrderStatusRef,
        on_delete=models.SET_NULL,
        db_column='new_status_id',
        null=True,
        blank=True,
        related_name='new_status_events',
        verbose_name="Новый статус"
    )
    old_service = models.ForeignKey(
        'portal.ServicesCatalog',
        on_delete=models.SET_NULL,
        db_column='old_service_id',
        null=True,
        blank=True,
        related_name='old_service_events',
        verbose_name="Старая услуга"
    )
    new_service = models.ForeignKey(
        'portal.ServicesCatalog',
        on_delete=models.SET_NULL,
        db_column='new_service_id',
        null=True,
        blank=True,
        related_name='new_service_events',
        verbose_name="Новая услуга"
    )
    old_object = models.ForeignKey(
        'portal.ServiceObject',
        on_delete=models.SET_NULL,
        db_column='old_object_id',
        null=True,
        blank=True,
        related_name='old_object_events',
        verbose_name="Старый объект"
    )
    new_object = models.ForeignKey(
        'portal.ServiceObject',
        on_delete=models.SET_NULL,
        db_column='new_object_id',
        null=True,
        blank=True,
        related_name='new_object_events',
        verbose_name="Новый объект"
    )
    old_responsible_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='old_responsible_user_id',
        null=True,
        blank=True,
        related_name='old_responsible_events',
        verbose_name="Старый ответственный"
    )
    new_responsible_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='new_responsible_user_id',
        null=True,
        blank=True,
        related_name='new_responsible_events',
        verbose_name="Новый ответственный"
    )
    is_visible_to_resident = models.BooleanField(default=False, verbose_name="Видно жителю")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'work_order_event_log'
        verbose_name = "Событие заявки"
        verbose_name_plural = "События заявок"
        ordering = ['-event_datetime']
        indexes = [
            models.Index(fields=['work_order', '-event_datetime'], name='idx_work_evlog_work_dt'),
            models.Index(fields=['company', 'department', '-event_datetime'], name='idx_work_evlog_comp_dept_dt'),
            models.Index(fields=['event_type_code', '-event_datetime'], name='idx_work_evlog_type_dt'),
        ]

    def __str__(self):
        return f"{self.event_type_code} - {self.work_order.work_order_no} ({self.event_datetime})"


class WorkOrderAttachment(models.Model):
    """Вложения заявки (request_mgmt.work_order_attachment)"""

    ATTACHMENT_KIND_CHOICES = [
        ('incoming_photo', 'Входящее фото'),
        ('result_photo', 'Фото результата'),
        ('document', 'Документ'),
        ('other', 'Другое'),
    ]

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        db_column='work_order_id',
        related_name='attachments',
        verbose_name="Заявка"
    )
    event = models.ForeignKey(
        WorkOrderEventLog,
        on_delete=models.SET_NULL,
        db_column='event_id',
        null=True,
        blank=True,
        related_name='attachments',
        verbose_name="Событие"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Загружен")
    uploaded_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        db_column='uploaded_by_user_id',
        null=True,
        blank=True,
        related_name='uploaded_attachments',
        verbose_name="Загружен пользователем"
    )
    attachment_kind = models.CharField(max_length=30, choices=ATTACHMENT_KIND_CHOICES, verbose_name="Тип вложения")
    mime_type = models.CharField(max_length=120, verbose_name="MIME-тип")
    file_name = models.CharField(max_length=255, verbose_name="Имя файла")
    file_size = models.BigIntegerField(validators=[MinValueValidator(0)], verbose_name="Размер (байт)")
    file_data = models.BinaryField(verbose_name="Содержимое файла")
    is_visible_to_resident = models.BooleanField(default=False, verbose_name="Видно жителю")
    sort_order = models.IntegerField(default=100, verbose_name="Порядок сортировки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый")

    class Meta:
        db_table = 'work_order_attachment'
        verbose_name = "Вложение заявки"
        verbose_name_plural = "Вложения заявок"
        ordering = ['work_order', 'sort_order', 'uploaded_at']
        constraints = [
            CheckConstraint(
                condition=Q(attachment_kind__in=['incoming_photo', 'result_photo', 'document', 'other']),
                name='ck_work_order_attachment_kind'
            ),
        ]
        indexes = [
            models.Index(fields=['work_order'], name='idx_work_attach_work_order'),
            models.Index(fields=['event'], name='idx_work_attach_event'),
            models.Index(fields=['attachment_kind'], name='idx_work_order_attachment_kind'),
        ]

    def __str__(self):
        return f"{self.get_attachment_kind_display()}: {self.file_name}"
