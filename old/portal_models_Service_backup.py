"""
АРХИВНАЯ КОПИЯ: Модель Service из portal/models.py (строки 77-131)

Дата архивации: 2026-01-14
Причина: Модель не используется в коде, дублирует services_catalog
Данные перенесены в services_catalog (tags/keywords)

Оригинал: portal/models.py класс Service (строки 77-131)
"""

from django.db import models


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


# Данные из этой таблицы были перенесены в services_catalog
# Соответствие:
# - plumbing (Сантехника) → Канализация, Санитария, Водоснабжение
# - heating (Отопление) → Отопление
# - electrical (Электричество) → Электричество
# - elevator (Лифт) → Лифты
