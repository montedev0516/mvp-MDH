"""Admin configuration for the dispatch app."""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from django.utils import timezone
from dispatch.models import (
    Order,
    Trip,
    Dispatch,
    DriverTruckAssignment,
    StatusHistory,
    Notification
)
from dispatch.models.log import OrderLog, TripLog


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order model."""
    
    list_display = (
        'order_number',
        'customer_name',
        'status',
        'pickup_date',
        'delivery_date',
        'load_total',
        'load_currency',
        'created_at'
    )
    list_filter = ('status', 'load_currency', 'created_at')
    search_fields = ('order_number', 'customer_name', 'origin', 'destination')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    """Admin interface for Trip model."""
    
    list_display = (
        'order',
        'status',
        'estimated_distance',
        'estimated_duration',
        'freight_value',
        'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('order__order_number',)
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    """Admin interface for Dispatch model."""
    
    list_display = (
        'order',
        'driver',
        'truck',
        'carrier',
        'status',
        'commission_amount',
        'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('order__order_number', 'driver__first_name', 'driver__last_name', 'truck__unit')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(DriverTruckAssignment)
class DriverTruckAssignmentAdmin(admin.ModelAdmin):
    """Admin interface for DriverTruckAssignment model."""
    
    list_display = (
        'driver',
        'truck',
        'status',
        'start_date',
        'end_date',
        'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('driver__first_name', 'driver__last_name', 'truck__unit')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(OrderLog)
class OrderLogAdmin(admin.ModelAdmin):
    """Admin interface for OrderLog model."""
    
    list_display = ('action', 'created_at', 'created_by')
    list_filter = ('action', 'created_at')
    search_fields = ('message',)
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(TripLog)
class TripLogAdmin(admin.ModelAdmin):
    """Admin interface for TripLog model."""
    
    list_display = ('trip', 'action', 'created_at', 'created_by')
    list_filter = ('action', 'created_at')
    search_fields = ('trip__trip_number', 'message')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):
    """Admin interface for StatusHistory model."""
    
    list_display = ('content_type', 'object_id', 'old_status', 'new_status', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('object_id', 'old_status', 'new_status')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for Notification model."""
    
    list_display = ('title', 'priority', 'status', 'created_at')
    list_filter = ('priority', 'status', 'created_at')
    search_fields = ('title', 'message')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
