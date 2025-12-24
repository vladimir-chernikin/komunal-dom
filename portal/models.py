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

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Создал")

    class Meta:
        verbose_name = "AI промпт"
        verbose_name_plural = "AI промпты"
        ordering = ['prompt_type', 'prompt_id']

    def __str__(self):
        return f"{self.prompt_type}: {self.title}"


class UserProfile(models.Model):
    """Расширенный профиль пользователя"""

    ROLE_CHOICES = [
        ('uk_user', 'Пользователь УК'),
        ('dba', 'DBA - менеджер данных'),
        ('django_admin', 'Администратор Django (ИТ)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='uk_user', verbose_name="Роль")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон")
    address = models.TextField(blank=True, null=True, verbose_name="Адрес")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_uk_user(self):
        return self.role in ['uk_user', 'dba']

    def is_uk_admin(self):
        return self.role in ['dba', 'django_admin']

    def is_dba(self):
        return self.role == 'dba'

    def is_django_admin(self):
        return self.role == 'django_admin'

    def has_admin_access(self):
        return self.role in ['dba', 'django_admin']


class Service(models.Model):
    """Услуги УК Аспект"""

    CATEGORY_CHOICES = [
        ('plumbing', 'Сантехника'),
        ('heating', 'Отопление'),
        ('electrical', 'Электрика'),
        ('elevator', 'Лифт'),
        ('building', 'Строительные работы'),
        ('cleaning', 'Уборка'),
        ('other', 'Другое'),
    ]

    INCIDENT_TYPE_CHOICES = [
        ('emergency', 'Аварийная'),
        ('planned', 'Плановая'),
        ('consultation', 'Консультация'),
    ]

    LOCATION_TYPE_CHOICES = [
        ('apartment', 'Квартира'),
        ('building', 'Подъезд/МКД'),
        ('territory', 'Придомовая территория'),
        ('common', 'Общее'),
    ]

    name = models.CharField(max_length=255, verbose_name="Название услуги")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name="Категория")
    object_type = models.CharField(max_length=50, verbose_name="Тип объекта")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPE_CHOICES, verbose_name="Тип инцидента")
    location_type = models.CharField(max_length=20, choices=LOCATION_TYPE_CHOICES, verbose_name="Тип локации")
    tags = models.TextField(blank=True, help_text="Теги через запятую", verbose_name="Теги")
    keywords = models.TextField(blank=True, help_text="Ключевые слова через запятую", verbose_name="Ключевые слова")
    description = models.TextField(blank=True, verbose_name="Описание")
    is_active = models.BooleanField(default=True, verbose_name="Активна")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ['category', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

    def get_tags_list(self):
        """Возвращает список тегов"""
        return [tag.strip() for tag in self.tags.split(',') if tag.strip()]

    def get_keywords_list(self):
        """Возвращает список ключевых слов"""
        return [kw.strip() for kw in self.keywords.split(',') if kw.strip()]
