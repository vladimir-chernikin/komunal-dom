# -*- coding: utf-8 -*-
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Расширенный профиль пользователя"""

    ROLE_CHOICES = [
        ('uk_user', 'Пользователь УК'),
        ('direktor_uk', 'Директор УК'),
        ('django_admin', 'Администратор Django (ИТ)'),
        ('executor', 'Исполнитель'),
        ('resident', 'Житель'),
    ]

    TIMEZONE_CHOICES = [
        ('Europe/Moscow', 'РњРѕСЃРєРІР° (UTC+3)'),
        ('Europe/Kaliningrad', 'Калининград (UTC+2)'),
        ('Europe/Samara', 'Самара (UTC+4)'),
        ('Asia/Yekaterinburg', 'Екатеринбург (UTC+5)'),
        ('Asia/Omsk', 'РћРјСЃРє (UTC+6)'),
        ('Asia/Krasnoyarsk', 'Красноярск (UTC+7)'),
        ('Asia/Irkutsk', 'Иркутск (UTC+8)'),
        ('Asia/Yakutsk', 'Якутск (UTC+9)'),
        ('Asia/Vladivostok', 'Владивосток (UTC+10)'),
        ('Asia/Magadan', 'Магадан (UTC+11)'),
        ('Asia/Kamchatka', 'Камчатка (UTC+12)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='resident', verbose_name="Роль")
    max_user_id = models.BigIntegerField(
        blank=True,
        null=True,
        unique=True,
        verbose_name="MAX user ID",
        help_text="Числовой ID пользователя из initData.user.id мини-приложения MAX.",
    )
    timezone = models.CharField(max_length=50, choices=TIMEZONE_CHOICES, default='Europe/Moscow', verbose_name="Часовой пояс")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    address = models.TextField(blank=True, null=True, verbose_name="Адрес")

    # Основная компания и подразделение (primary)
    primary_company = models.ForeignKey(
        'nsi.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Основная компания",
        related_name='primary_users',
        help_text="Основная компания пользователя для 90% кейсов"
    )
    primary_department = models.ForeignKey(
        'work_orders.CompanyDepartment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Основное подразделение",
        related_name='primary_users',
        help_text="Основное подразделение пользователя для 90% кейсов"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    # Дополнительные поля для сотрудников
    specialization = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[(None, 'Не указана'), ('plumber', 'Сантехник'), ('electrician', 'Электрик'), ('general_worker', 'Разнорабочий')],
        verbose_name='Специализация исполнителя'
    )
    job_title = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        choices=[(None, 'Не указана'), ('director', 'Директор'), ('manager', 'Менеджер УК'), ('dispatcher', 'Диспетчер'), ('chief_engineer', 'Главный инженер')],
        verbose_name='Должность'
    )
    responsibilities = models.TextField(
        blank=True,
        null=True,
        help_text='Описание обязанностей сотрудника',
        verbose_name='Обязанности'
    )

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_uk_user(self):
        return self.role in ['uk_user', 'direktor_uk']

    def is_uk_admin(self):
        return self.role in ['direktor_uk', 'django_admin']

    def is_director_uk(self):
        return self.role == 'direktor_uk'

    def is_django_admin(self):
        return self.role == 'django_admin'

    def has_admin_access(self):
        return self.role in ['direktor_uk', 'django_admin']


class ServicesCatalog(models.Model):
    """Услуги из БД services_catalog (unmanaged модель)

    РќРћР'РђРЇ РЎРўР РЈРљРўРЈР Рђ (СЃ 2026-03-26):
    - 44 услуги (матрица 11 категорий × 2 типа × 2 локализации)
    - FK поля: type_id, category_id, localization_id
    - Текстовые поля сохранены для обратной совместимости

    ВОССТАНОВЛЕНО (2026-03-26):
    - Добавлены ForeignKey поля для FK-структуры БД
    - Текстовые поля устарели, но временно оставлены
    """

    service_id = models.IntegerField(primary_key=True, verbose_name="ID услуги")
    scenario_name = models.CharField(max_length=255, verbose_name="Название услуги")

    # ========================================
    # FK ПОЛЯ (ВОССТАНОВЛЕНЫ - 2026-03-26)
    # ========================================
    # Привязка к существующим БД-колонкам: type_id, category_id, localization_id
    # Используем db_column для маппинга на существующие колонки (без создания новых)

    type = models.ForeignKey(
        'nsi.RefServiceType',
        db_column='type_id',
        on_delete=models.PROTECT,
        verbose_name="Тип услуги",
        related_name='+',
        help_text="Инцидент или Запрос"
    )

    category = models.ForeignKey(
        'nsi.RefCategory',
        db_column='category_id',
        on_delete=models.PROTECT,
        verbose_name="Категория",
        related_name='+',
        help_text="Категория услуги (11 категорий)"
    )

    localization = models.ForeignKey(
        'nsi.RefLocalization',
        db_column='localization_id',
        on_delete=models.PROTECT,
        verbose_name="Локализация",
        related_name='+',
        help_text="Общедомовое или Индивидуальное"
    )

    # ========================================
    # УСТАРЕВШИЕ ТЕКСТОВЫЕ ПОЛЯ (ВРЕМЕННО ОСТАВЛЕНЫ)
    # ========================================
    # ВНИМАНИЕ: Эти поля устарели и сохранены ТОЛЬКО для обратной совместимости.
    # Будут удалены после обновления всех SQL-запросов и проверки приложения.
    # НЕ ИСПОЛЬЗОВАТЬ в новом коде - используйте FK поля (type, category, localization).

    type_name = models.CharField(
        max_length=100,
        verbose_name="Тип услуги (устарело, использовать 'type')",
        help_text="ВРЕМЕННО: Устаревшее текстовое поле. Используйте FK поле 'type'."
    )

    localization_name = models.CharField(
        max_length=100,
        verbose_name="Локализация (устарело, использовать 'localization')",
        help_text="ВРЕМЕННО: Устаревшее текстовое поле. Используйте FK поле 'localization'."
    )

    category_name = models.CharField(
        max_length=255,
        verbose_name="Категория (устарело, использовать 'category')",
        help_text="ВРЕМЕННО: Устаревшее текстовое поле. Используйте FK поле 'category'."
    )

    # ========================================
    # ОСТАЛЬНЫЕ ПОЛЯ (без изменений)
    # ========================================

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Описание"
    )

    route_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Маршрут"
    )

    is_internal = models.BooleanField(
        default=False,
        verbose_name="Служебная услуга"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления"
    )

    class Meta:
        managed = False  # НЕ управлять Django (таблица уже существует)
        db_table = 'services_catalog'
        verbose_name = "Услуга"
        verbose_name_plural = "Справочник услуг"
        ordering = ['category', 'scenario_name']  # Используем FK поле

    def __str__(self):
        return f"{self.scenario_name} (ID: {self.service_id})"


class Unit(models.Model):
    """Помещения (unmanaged модель, таблица units)."""

    unit_id = models.AutoField(primary_key=True, db_column='unit_id', verbose_name='ID помещения')
    unit_number = models.CharField(max_length=30, blank=True, null=True, verbose_name="Номер помещения")
    building_id = models.IntegerField(verbose_name="ID здания")

    class Meta:
        managed = False
        db_table = 'units'
        verbose_name = "Помещение"
        verbose_name_plural = "Помещения"
        ordering = ['unit_id']

    def __str__(self):
        return self.unit_number or f"Помещение #{self.unit_id}"

class ServiceObject(models.Model):
    """Объекты обслуживания (unmanaged модель, таблица service_objects)"""

    service_object_id = models.AutoField(primary_key=True, db_column='service_object_id', verbose_name='ID объекта')
    building_id = models.IntegerField(verbose_name="ID здания")
    unit_id = models.IntegerField(blank=True, null=True, verbose_name="ID помещения")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(verbose_name="Создан")

    class Meta:
        managed = False  # НЕ управлять Django (таблица уже существует)
        db_table = 'service_objects'
        verbose_name = "Объект обслуживания"
        verbose_name_plural = "Объекты обслуживания"
        ordering = ['service_object_id']
        indexes = [
            models.Index(fields=['building_id'], name='idx_srvobj_building'),
            models.Index(fields=['building_id', 'is_active'], name='idx_srvobj_building_active'),
        ]

    def get_building(self):
        from kladr.models import Building

        return (
            Building.objects.select_related(
                'address_object__type',
                'address_object__parent__type',
                'address_object__parent__parent__type',
            )
            .filter(pk=self.building_id)
            .first()
        )

    def get_unit(self):
        if not self.unit_id:
            return None
        return Unit.objects.filter(pk=self.unit_id).first()

    def get_address_display(self):
        building = self.get_building()
        unit = self.get_unit()

        if building:
            address = building.get_full_address()
        else:
            address = f"Здание #{self.building_id}"

        if unit and unit.unit_number:
            address = f"{address}, пом. {unit.unit_number}"
        elif self.unit_id:
            address = f"{address}, помещение #{self.unit_id}"

        return address

    def get_search_label(self):
        return f"{self.get_address_display()} [объект {self.service_object_id}]"

    def __str__(self):
        return self.get_search_label()


def search_service_objects(search_term, queryset=None, limit=20):
    """Поиск объектов обслуживания по ID, адресу дома и номеру помещения."""
    from kladr.models import Building

    search_term = (search_term or '').strip()
    queryset = (queryset or ServiceObject.objects.all()).filter(is_active=True)

    if not search_term:
        return queryset.none()

    filters = Q()

    if search_term.isdigit():
        numeric_value = int(search_term)
        filters |= Q(service_object_id=numeric_value)
        filters |= Q(building_id=numeric_value)
        filters |= Q(unit_id=numeric_value)

    building_ids = list(
        Building.objects.filter(
            Q(house_number__icontains=search_term)
            | Q(address_object__name__icontains=search_term)
            | Q(address_object__parent__name__icontains=search_term)
            | Q(address_object__parent__parent__name__icontains=search_term)
        )
        .values_list('id', flat=True)[: limit * 10]
    )
    if building_ids:
        filters |= Q(building_id__in=building_ids)

    unit_ids = list(
        Unit.objects.filter(unit_number__icontains=search_term)
        .values_list('unit_id', flat=True)[: limit * 10]
    )
    if unit_ids:
        filters |= Q(unit_id__in=unit_ids)

    if not filters.children:
        return queryset.none()

    return queryset.filter(filters).order_by('service_object_id').distinct()[:limit]
