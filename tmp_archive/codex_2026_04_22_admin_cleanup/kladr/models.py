from django.contrib.auth.models import User
from django.db import models


class KladrObjectType(models.Model):
    """KLADR object types."""

    LEVEL_CHOICES = [
        (1, "Регион"),
        (2, "Район"),
        (3, "Город"),
        (4, "Населенный пункт"),
        (5, "Улица"),
    ]

    code = models.CharField(max_length=10, unique=True, verbose_name="Код типа")
    name = models.CharField(max_length=100, verbose_name="Название типа")
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, verbose_name="Уровень")
    short_name = models.CharField(max_length=20, blank=True, verbose_name="Короткое название")

    class Meta:
        verbose_name = "Тип объекта КЛАДР"
        verbose_name_plural = "Типы объектов КЛАДР"
        ordering = ["level", "name"]

    def __str__(self):
        return f"{self.name} (уровень {self.get_level_display()})"


class KladrAddressObject(models.Model):
    """Address objects imported from KLADR."""

    name = models.CharField(max_length=255, verbose_name="Название")
    type = models.ForeignKey(KladrObjectType, on_delete=models.PROTECT, verbose_name="Тип объекта")
    code = models.CharField(max_length=20, unique=True, verbose_name="Код КЛАДР")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name="Родительский объект",
    )
    fias_object_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID ФИАС")
    fias_object_guid = models.UUIDField(null=True, blank=True, verbose_name="GUID ФИАС")
    fias_level_id = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Уровень ФИАС")
    fias_address_type = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Вид адреса ФИАС",
    )
    zip_code = models.CharField(max_length=6, blank=True, null=True, verbose_name="Почтовый индекс")
    okato = models.CharField(max_length=11, blank=True, null=True, verbose_name="ОКАТО")
    oktmo = models.CharField(max_length=11, blank=True, null=True, verbose_name="ОКТМО")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Создал")

    class Meta:
        verbose_name = "Адресный объект КЛАДР"
        verbose_name_plural = "Адресные объекты КЛАДР"
        ordering = ["type__level", "name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["fias_object_id"]),
            models.Index(fields=["fias_object_guid"]),
            models.Index(fields=["fias_level_id"]),
            models.Index(fields=["type", "name"]),
            models.Index(fields=["parent"]),
            models.Index(fields=["zip_code"]),
        ]

    def __str__(self):
        prefix = f"{self.type.short_name} " if self.type and self.type.short_name else ""
        return f"{prefix}{self.name}".strip()

    def get_full_address(self):
        parts = []
        current = self
        while current:
            if current == self:
                parts.append(str(current))
            else:
                prefix = f"{current.type.short_name} " if current.type and current.type.short_name else ""
                parts.append(f"{prefix}{current.name}".strip())
            current = current.parent
        return ", ".join(reversed(parts))


class Building(models.Model):
    """Building linked to a street-level address object."""

    address_object = models.ForeignKey(
        KladrAddressObject,
        on_delete=models.CASCADE,
        limit_choices_to={"type__level__lte": 5},
        verbose_name="Адресный объект",
    )
    house_number = models.CharField(max_length=20, verbose_name="Номер дома")
    building_type = models.CharField(max_length=50, blank=True, verbose_name="Тип дома")
    porch_count = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Количество подъездов")
    floor_count = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Этажность")
    has_elevator = models.BooleanField(default=False, verbose_name="Есть лифт")
    square_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Общая площадь (м2)",
    )
    fias_object_id = models.BigIntegerField(null=True, blank=True, verbose_name="ID ФИАС")
    fias_object_guid = models.UUIDField(null=True, blank=True, verbose_name="GUID ФИАС")
    fias_level_id = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Уровень ФИАС")
    fias_address_type = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Вид адреса ФИАС",
    )
    fias_full_name = models.CharField(max_length=500, blank=True, null=True, verbose_name="Полный адрес ФИАС")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Создал")

    class Meta:
        verbose_name = "Здание"
        verbose_name_plural = "Здания"
        unique_together = ["address_object", "house_number"]
        ordering = ["address_object__name", "house_number"]
        indexes = [
            models.Index(fields=["fias_object_id"]),
            models.Index(fields=["fias_object_guid"]),
            models.Index(fields=["fias_level_id"]),
        ]

    def __str__(self):
        return f"{self.address_object}, д. {self.house_number}"

    def get_full_address(self):
        return f"{self.address_object.get_full_address()}, д. {self.house_number}"

    def get_fias_identity(self):
        return {
            "fias_object_id": self.fias_object_id,
            "fias_object_guid": str(self.fias_object_guid) if self.fias_object_guid else None,
            "fias_level_id": self.fias_level_id,
            "fias_address_type": self.fias_address_type,
            "fias_full_name": self.fias_full_name,
        }


class ServiceArea(models.Model):
    """Service area for management zones."""

    name = models.CharField(max_length=255, verbose_name="Название зоны")
    description = models.TextField(blank=True, verbose_name="Описание")
    buildings = models.ManyToManyField(Building, verbose_name="Здания в зоне")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Создал")

    class Meta:
        verbose_name = "Зона обслуживания"
        verbose_name_plural = "Зоны обслуживания"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_building_count(self):
        return self.buildings.count()


class DataImportLog(models.Model):
    """Audit log for KLADR import jobs."""

    OPERATION_TYPES = [
        ("import", "Импорт"),
        ("update", "Обновление"),
        ("delete", "Удаление"),
    ]

    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPES, verbose_name="Тип операции")
    file_name = models.CharField(max_length=255, verbose_name="Имя файла")
    records_processed = models.PositiveIntegerField(verbose_name="Обработано записей")
    records_successful = models.PositiveIntegerField(verbose_name="Успешно")
    records_failed = models.PositiveIntegerField(default=0, verbose_name="Ошибок")
    error_details = models.TextField(blank=True, verbose_name="Детали ошибок")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Начато")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Запустил")

    class Meta:
        verbose_name = "Лог импорта данных"
        verbose_name_plural = "Логи импорта данных"
        ordering = ["-started_at"]

    def __str__(self):
        started_at = self.started_at.strftime("%d.%m.%Y %H:%M") if self.started_at else "-"
        return f"{self.get_operation_type_display()} - {self.file_name} ({started_at})"
