from django.contrib import admin
from fleet.models.carrier import Carrier
from fleet.models.driver import Driver, DriverLicense
from fleet.models.truck import Truck
from .models import (
    DriverEmployment,
    Customer,
    Organization,
)


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ('name', 'legal_name', 'business_number', 'mc_number', 'dot_number', 'tax_rate', 'tax_currency', 'status', 'is_active', 'tenant')
    list_filter = ('status', 'is_active', 'tax_currency', 'country', 'state', 'tenant')
    search_fields = ('name', 'legal_name', 'business_number', 'mc_number', 'dot_number')


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'license_number', 'employee_id', 'carrier')
    list_filter = ('carrier', 'country', 'state')
    search_fields = ('first_name', 'last_name', 'license_number', 'employee_id', 'email', 'phone')


@admin.register(DriverLicense)
class DriverLicenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'license_number', 'expiry_date', 'license_type', 'license_class')
    list_filter = ('license_type', 'license_class', 'country', 'state', 'province')
    search_fields = ('name', 'license_number', 'public_safety_commission')
    readonly_fields = ('llm_model_name', 'uploaded_file_name', 'file_save_path')


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('unit', 'plate', 'make', 'model', 'year', 'status', 'carrier')
    list_filter = ('status', 'ownership_type', 'is_active', 'is_trailer', 'carrier')
    search_fields = ('unit', 'plate', 'vin', 'make', 'model')


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'commission_percentage', 'commission_currency', 'tenant']
    list_filter = ['commission_currency', 'tenant']
    search_fields = ['name', 'address']
