from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from models.models import BaseModel
from django.utils import timezone

class StatusHistory(BaseModel):
    """
    Generic model to track status changes across all dispatch-related models
    """
    # Content type for generic relation
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Status change details
    old_status = models.CharField(max_length=50, null=True, blank=True)
    new_status = models.CharField(max_length=50)
    changed_at = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='status_changes'
    )

    # Additional context
    notes = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = "Status History"
        verbose_name_plural = "Status Histories"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['changed_at']),
        ]

    def __str__(self):
        old_status_display = self.old_status if self.old_status else 'Initial'
        return f"{self.content_type} - {self.object_id}: {old_status_display} → {self.new_status}"

    @classmethod
    def log_status_change(cls, obj, old_status, new_status, user=None, notes=None, metadata=None):
        """
        Create a status history entry for the given object
        """
        content_type = ContentType.objects.get_for_model(obj)
        
        return cls.objects.create(
            content_type=content_type,
            object_id=obj.id,
            old_status=old_status or None,
            new_status=new_status,
            changed_by=user,
            notes=notes,
            metadata=metadata or {},
            tenant=obj.tenant
        ) 