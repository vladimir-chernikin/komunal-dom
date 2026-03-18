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
