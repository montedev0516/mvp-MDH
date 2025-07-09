"""Model for handling file uploads in the dispatch system."""

from django.db import models
from django.conf import settings
from models.models import BaseModel


class UploadFile(BaseModel):
    """Model for storing uploaded files."""

    file = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    order = models.ForeignKey(
        "dispatch.Order",
        on_delete=models.CASCADE,
        related_name="files",
        null=True,
        blank=True,
    )
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Upload {self.id} - {self.uploaded_at}" 