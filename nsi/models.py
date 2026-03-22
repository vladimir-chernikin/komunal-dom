from django.db import models


class Company(models.Model):
    """Справочник компаний"""

    name = models.CharField(max_length=255, verbose_name="Наименование")
    full_name = models.CharField(max_length=500, blank=True, null=True, verbose_name="Полное наименование")
    domain = models.CharField(max_length=255, blank=True, null=True, verbose_name="Домен")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Телефон для приема заявок")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Компания"
        verbose_name_plural = "Компании"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (ID: {self.id})"


class EquipmentType(models.Model):
    """Справочник видов общедомового оборудования"""

    name = models.CharField(max_length=255, verbose_name="Наименование")
    description_for_llm = models.TextField(blank=True, null=True, verbose_name="Описание для LLM", help_text="Подробное описание для использования в AI-системе")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Вид оборудования"
        verbose_name_plural = "Виды общедомового оборудования"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (ID: {self.id})"


class RefCategory(models.Model):
    """Справочник категорий услуг ЖКХ"""

    category_id = models.SmallIntegerField(primary_key=True, verbose_name="ID категории")
    category_name = models.CharField(max_length=255, verbose_name="Наименование категории")
    llm_description = models.TextField(verbose_name="Описание для LLM", help_text="Текстовое описание для использования в AI-системах классификации")
    is_default = models.BooleanField(default=False, verbose_name="Категория по умолчанию", help_text="Только одна категория может быть помечена как default")
    dev_notes = models.TextField(blank=True, null=True, verbose_name="Заметки разработчика")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        db_table = 'ref_categories'
        verbose_name = "Категория услуг"
        verbose_name_plural = "Категории услуг ЖКХ"
        ordering = ['category_id']

    def __str__(self):
        return f"{self.category_id} + \"{self.category_name}\""

    def save(self, *args, **kwargs):
        """Переопределяем save для обеспечения единственности is_default"""
        if self.is_default:
            # Сбрасываем is_default у всех остальных записей
            RefCategory.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
