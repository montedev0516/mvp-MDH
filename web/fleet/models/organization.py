from django.db import models
from models.models import BaseModel, Currency


class Organization(BaseModel):
    """Organization model for managing company information and commission settings"""
    
    # Basic Information
    name = models.CharField(
        max_length=255,
        verbose_name="Organization Name",
        help_text="The name of the organization"
    )
    address = models.TextField(
        verbose_name="Address",
        help_text="Full address of the organization"
    )
    
    # Commission Settings
    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=12.0,
        verbose_name="Commission Percentage",
        help_text="Default commission percentage for dispatches"
    )
    commission_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.CAD,
        verbose_name="Commission Currency",
        help_text="Default currency for commission amounts"
    )
    
    # Relationships
    tenant = models.OneToOneField(
        "tenant.Tenant",
        on_delete=models.CASCADE,
        related_name="organization",
        help_text="Associated tenant"
    )
    carrier = models.OneToOneField(
        "fleet.Carrier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organization",
        help_text="Associated carrier"
    )
    
    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["name"]
    
    def __str__(self):
        return self.name 