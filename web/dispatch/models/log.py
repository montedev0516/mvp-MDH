"""Models for logging actions in the dispatch system."""

from django.db import models
from django.utils import timezone
from models.models import BaseModel
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class BaseLog(BaseModel):
    """Base model for all log entries."""

    ACTION_STATUS_CHANGE = "status_change"
    ACTION_CREATED = "created"
    ACTION_UPDATED = "updated"
    ACTION_DELETED = "deleted"
    ACTION_COMMENT = "comment"

    ACTION_CHOICES = [
        (ACTION_STATUS_CHANGE, "Status Change"),
        (ACTION_CREATED, "Created"),
        (ACTION_UPDATED, "Updated"),
        (ACTION_DELETED, "Deleted"),
        (ACTION_COMMENT, "Comment"),
    ]

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="%(class)s_entries",
    )
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE, related_name="%(class)s_entries")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class OrderLog(BaseLog):
    """Log entries for order actions."""

    class Meta(BaseLog.Meta):
        verbose_name = "Order Log"
        verbose_name_plural = "Order Logs"
        db_table = 'dispatch_order_log'

    def __str__(self):
        return f"Order Log {self.id} - {self.action}"


class TripLog(BaseLog):
    """Log entries for trip actions."""

    trip = models.ForeignKey(
        "dispatch.Trip",
        on_delete=models.CASCADE,
        related_name="logs",
    )

    class Meta(BaseLog.Meta):
        verbose_name = "Trip Log"
        verbose_name_plural = "Trip Logs"
        db_table = 'dispatch_trip_log'

    def __str__(self):
        return f"Trip Log {self.id} - {self.action}" 