from django.db import models
from django.contrib.auth.models import User


class AIPrompt(models.Model):
    """AI промпты для бота"""

    PROMPT_TYPES = [
        ('system', 'Системный промпт'),
        ('greeting', 'Приветствие'),
        ('address_check', 'Проверка адреса'),
        ('address_not_found', 'Адрес не найден'),
        ('farewell', 'Прощание'),
        ('error', 'Ошибка'),
        ('profanity_warning', 'Предупреждение о ругательствах'),
        ('default', 'Ответ по умолчанию'),
    ]

    prompt_id = models.CharField(max_length=50, unique=True, verbose_name="ID промпта")
    prompt_type = models.CharField(max_length=20, choices=PROMPT_TYPES, verbose_name="Тип промпта")
    title = models.CharField(max_length=255, verbose_name="Название")
    description = models.TextField(blank=True, verbose_name="Описание для чего используется")
    content = models.TextField(verbose_name="Содержание промпта")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_test = models.BooleanField(default=False, verbose_name="Тестовый", help_text="True = тестовый (для экспериментов), False = боевой (используется в продакшне)")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Создал")

    class Meta:
        verbose_name = "AI и Промпты: Промпт"
        verbose_name_plural = "AI и Промпты: Промпты"
        ordering = ['prompt_type', 'prompt_id']

    def __str__(self):
        return f"{self.prompt_type}: {self.title}"


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
        ('Europe/Moscow', 'Москва (UTC+3)'),
        ('Europe/Kaliningrad', 'Калининград (UTC+2)'),
        ('Europe/Samara', 'Самара (UTC+4)'),
        ('Asia/Yekaterinburg', 'Екатеринбург (UTC+5)'),
        ('Asia/Omsk', 'Омск (UTC+6)'),
        ('Asia/Krasnoyarsk', 'Красноярск (UTC+7)'),
        ('Asia/Irkutsk', 'Иркутск (UTC+8)'),
        ('Asia/Yakutsk', 'Якутск (UTC+9)'),
        ('Asia/Vladivostok', 'Владивосток (UTC+10)'),
        ('Asia/Magadan', 'Магадан (UTC+11)'),
        ('Asia/Kamchatka', 'Камчатка (UTC+12)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='resident', verbose_name="Роль")
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
        choices=[(None, 'Не указана'), ('manager', 'Менеджер УК'), ('dispatcher', 'Диспетчер'), ('chief_engineer', 'Главный инженер')],
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


class SemanticPattern(models.Model):
    """Семантический паттерн для классификации сообщений"""

    PATTERN_TYPES = [
        ('incident', 'Инцидент/Авария'),
        ('water', 'Водоснабжение/Канализация'),
        ('electricity', 'Электричество'),
        ('heating', 'Отопление'),
        ('gas', 'Газ'),
        ('elevator', 'Лифт'),
        ('door', 'Двери/Замки'),
        ('window', 'Окна'),
        ('roof', 'Крыша'),
        ('other', 'Другое'),
    ]

    pattern_type = models.CharField(
        max_length=50,
        choices=PATTERN_TYPES,
        db_index=True,
        verbose_name='Тип паттерна'
    )

    keyword = models.CharField(
        max_length=100,
        verbose_name='Ключевое слово'
    )

    weight = models.FloatField(
        default=1.0,
        verbose_name='Вес',
        help_text='Вес keyword (0.1 - 10.0). Отрицательный = инверсия.'
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name='Активен'
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name='Заметки'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Создан'
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Обновлен'
    )

    class Meta:
        verbose_name = 'Семантический паттерн'
        verbose_name_plural = 'Семантические паттерны'
        ordering = ['pattern_type', '-weight', 'keyword']
        indexes = [
            models.Index(fields=['pattern_type']),
            models.Index(fields=['keyword']),
            models.Index(fields=['is_active']),
        ]
        unique_together = [['pattern_type', 'keyword']]

    def __str__(self):
        return f"{self.pattern_type}: {self.keyword} (вес: {self.weight})"


class ServicesCatalog(models.Model):
    """Услуги из БД services_catalog (unmanaged модель)

    НОВАЯ СТРУКТУРА (с 2026-03-26):
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


class ServiceObject(models.Model):
    """Объекты обслуживания (unmanaged модель, таблица service_objects)"""

    service_object_id = models.IntegerField(primary_key=True, verbose_name="ID объекта")
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

    def __str__(self):
        if self.unit_id:
            return f"Объект #{self.service_object_id}: здание {self.building_id} - помещение {self.unit_id}"
        return f"Объект #{self.service_object_id}: здание {self.building_id}"

