from django.contrib import admin
from .models import KladrObjectType, KladrAddressObject, Building, ServiceArea, DataImportLog


@admin.register(KladrObjectType)
class KladrObjectTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'level', 'short_name')
    list_filter = ('level',)
    search_fields = ('code', 'name', 'short_name')
    ordering = ('level', 'name')


@admin.register(KladrAddressObject)
class KladrAddressObjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'code', 'parent', 'is_active')
    list_filter = ('type__level', 'is_active')
    search_fields = ('name', 'code', 'zip_code')
    ordering = ('type__level', 'name')
    raw_id_fields = ('parent',)


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('address_object', 'house_number', 'building_type', 'porch_count', 'floor_count', 'has_elevator')
    list_filter = ('building_type', 'has_elevator')
    search_fields = ('address_object__name', 'house_number')
    ordering = ('address_object__name', 'house_number')


@admin.register(ServiceArea)
class ServiceAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_building_count')
    filter_horizontal = ('buildings',)
    search_fields = ('name', 'description')


@admin.register(DataImportLog)
class DataImportLogAdmin(admin.ModelAdmin):
    list_display = ('operation_type', 'file_name', 'records_processed', 'records_successful', 'records_failed', 'started_at')
    list_filter = ('operation_type', 'started_at')
    readonly_fields = ('started_at', 'completed_at')
