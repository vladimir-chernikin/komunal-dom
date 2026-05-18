from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class Building(models.Model):
    fias_guid = models.UUIDField(null=True, blank=True, unique=True)
    street_fias_guid = models.UUIDField(null=True, blank=True)
    house_number = models.CharField(max_length=40)
    full_address = models.TextField()
    geo_lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    geo_lon = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    timezone = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="address_buildings_created",
    )

    class Meta:
        db_table = 'address"."building'
        constraints = [
            models.UniqueConstraint(
                fields=["street_fias_guid", "house_number"],
                condition=Q(fias_guid__isnull=True),
                name="uq_address_building_street_house_without_house_guid",
            ),
        ]
        indexes = [
            models.Index(fields=["street_fias_guid"], name="idx_addr_building_street_guid"),
            models.Index(fields=["house_number"], name="idx_addr_building_house_no"),
            models.Index(fields=["geo_lat", "geo_lon"], name="idx_addr_building_geo"),
        ]
        ordering = ["full_address", "id"]

    def __str__(self):
        return self.full_address

    def get_full_address(self):
        return self.full_address


class Unit(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name="units")
    unit_number = models.CharField(max_length=30)
    fias_guid = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'address"."unit'
        constraints = [
            models.UniqueConstraint(fields=["building", "unit_number"], name="uq_address_unit_building_number"),
            models.UniqueConstraint(
                fields=["fias_guid"],
                condition=Q(fias_guid__isnull=False),
                name="uq_address_unit_fias_guid",
            ),
        ]
        indexes = [models.Index(fields=["building", "unit_number"], name="idx_addr_unit_building_number")]
        ordering = ["building_id", "unit_number", "id"]

    def __str__(self):
        return self.unit_number


class ImportBatch(models.Model):
    STATUS_CHOICES = [("uploaded", "uploaded"), ("validated", "validated"), ("imported", "imported"), ("failed", "failed")]

    company_id = models.IntegerField()
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="address_import_batches")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    planned_date_from = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")

    class Meta:
        db_table = 'address"."import_batch'
        ordering = ["-uploaded_at", "-id"]


class ImportRow(models.Model):
    FINAL_STATUS_CHOICES = [("ready", "ready"), ("blocked", "blocked"), ("clarify", "clarify"), ("imported", "imported"), ("error", "error")]

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_no = models.PositiveIntegerField()
    raw_address = models.TextField(blank=True, default="")
    city_main = models.CharField(max_length=255, blank=True, default="")
    district = models.CharField(max_length=255, blank=True, default="")
    city_fact = models.CharField(max_length=255, blank=True, default="")
    street = models.CharField(max_length=255, blank=True, default="")
    house = models.CharField(max_length=64, blank=True, default="")
    unit_number = models.CharField(max_length=30, blank=True, default="")
    building_fias_guid = models.CharField(max_length=20, blank=True, default="")
    house_parse_status = models.CharField(max_length=30, blank=True, default="")
    house_fias_status = models.CharField(max_length=30, blank=True, default="")
    binding_status = models.CharField(max_length=30, blank=True, default="")
    unit_status = models.CharField(max_length=30, blank=True, default="")
    final_status = models.CharField(max_length=20, choices=FINAL_STATUS_CHOICES, blank=True, default="")
    comment = models.TextField(blank=True, default="")

    class Meta:
        db_table = 'address"."import_row'
        constraints = [models.UniqueConstraint(fields=["batch", "row_no"], name="uq_address_import_row_batch_row_no")]
        ordering = ["batch_id", "row_no", "id"]
