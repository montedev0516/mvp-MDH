import uuid
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.utils import timezone
from models.models import BaseModel


class Notification(BaseModel):
    """
    Model for storing notifications related to various events in the system.
    """
    NOTIFICATION_TYPES = [
        ('status_change', 'Status Change'),
        ('assignment_created', 'Assignment Created'),
        ('assignment_updated', 'Assignment Updated'),
        ('assignment_cancelled', 'Assignment Cancelled'),
        ('driver_assigned', 'Driver Assigned'),
        ('truck_assigned', 'Truck Assigned'),
        ('order_created', 'Order Created'),
        ('order_updated', 'Order Updated'),
        ('order_cancelled', 'Order Cancelled'),
        ('order_completed', 'Order Completed'),
        ('trip_started', 'Trip Started'),
        ('trip_delayed', 'Trip Delayed'),
        ('trip_completed', 'Trip Completed'),
        ('trip_location_updated', 'Trip Location Updated'),
        ('dispatch_created', 'Dispatch Created'),
        ('dispatch_assigned', 'Dispatch Assigned'),
        ('dispatch_in_transit', 'Dispatch In Transit'),
        ('dispatch_delivered', 'Dispatch Delivered'),
        ('dispatch_completed', 'Dispatch Completed'),
        ('dispatch_cancelled', 'Dispatch Cancelled'),
        ('driver_unavailable', 'Driver Unavailable'),
        ('truck_unavailable', 'Truck Unavailable'),
        ('driver_duty_exceeded', 'Driver Duty Hours Exceeded')
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('read', 'Read'),
        ('error', 'Error')
    ]

    type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='status_change')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    title = models.CharField(max_length=255)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Generic relation to any model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Recipients
    recipient_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='notifications',
        blank=True
    )
    recipient_groups = models.ManyToManyField(
        'auth.Group',
        related_name='notifications',
        blank=True
    )
    recipient_emails = models.JSONField(default=list, blank=True)

    # Tenant relationship
    tenant = models.ForeignKey('tenant.Tenant', on_delete=models.CASCADE)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.type} - {self.title} ({self.status})"

    def mark_as_sent(self):
        """Mark the notification as sent."""
        self.status = 'sent'
        self.sent_at = models.timezone.now()
        self.save()

    def mark_as_read(self):
        """Mark the notification as read."""
        self.status = 'read'
        self.read_at = models.timezone.now()
        self.save()

    def mark_as_error(self):
        """Mark the notification as having an error."""
        self.status = 'error'
        self.save()

    @classmethod
    def create_status_change_notification(cls, obj, old_status, new_status, priority='medium'):
        """
        Create a notification for a status change
        """
        content_type = ContentType.objects.get_for_model(obj)
        model_name = obj._meta.verbose_name.title()
        
        title = f"{model_name} Status Changed: {old_status} → {new_status}"
        message = (
            f"{model_name} {obj} has changed status from {old_status} to {new_status}.\n"
            f"Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        notification = cls.objects.create(
            content_type=content_type,
            object_id=obj.id,
            type='status_change',
            priority=priority,
            title=title,
            message=message,
            metadata={
                'old_status': str(old_status),
                'new_status': str(new_status),
                'model': model_name,
                'object_str': str(obj)
            },
            tenant=obj.tenant
        )
        
        return notification 