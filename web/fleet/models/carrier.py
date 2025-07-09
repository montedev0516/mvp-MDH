from django.db import models
from models.models import BaseModel, Currency
from django.core.validators import RegexValidator


# Validators
# phone_validator = RegexValidator(
#     # regex=r'^\+?1?\d{10}$',
#     message="Phone number must be in the format: '+1234567890'")

zip_code_validator = RegexValidator(
    regex=r'^\d{5}$',
    message="Zip code must be in the format: '12345'")

class CarrierStatus(models.TextChoices):
    """Status of the carrier"""
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    SUSPENDED = "suspended", "Suspended"
    BLACKLISTED = "blacklisted", "Blacklisted"
    
class Carrier(BaseModel):
    # Core Information
    name = models.CharField(
        max_length=100, 
        verbose_name="Carrier Name", 
        help_text="The name of the carrier")
    legal_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Legal Name", 
        help_text="The legal name of the carrier")
    business_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Business Number", 
        help_text="The business number of the carrier")

    mc_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        unique=True, 
        verbose_name="MC Number", 
        help_text="The MC number of the carrier")
    dot_number = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        unique=True)

    # Contact Information
    email = models.EmailField(verbose_name="Email Address")
    phone = models.CharField(max_length=20, verbose_name="Phone Number")
    website = models.URLField(blank=True, null=True, verbose_name="Website URL")

    # Address Information
    address = models.TextField(verbose_name="Address")
    city = models.CharField(max_length=50, null=True, blank=True, verbose_name="City")
    state = models.CharField(max_length=50, null=True, blank=True, verbose_name="State")
    zip_code = models.CharField(max_length=10, null=True, blank=True, validators=[zip_code_validator], verbose_name="Zip Code")
    country = models.CharField(max_length=50, null=True, blank=True, verbose_name="Country")

    # Fleet Information
    total_trucks = models.IntegerField(default=0, verbose_name="Total Trucks", help_text="The total number of trucks the carrier has")
    total_drivers = models.IntegerField(default=0, verbose_name="Total Drivers", help_text="The total number of drivers the carrier has")

    # Tax Information
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=13.0,
        verbose_name="Tax Rate",
        help_text="Tax percentage rate for this carrier"
    )
    tax_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.CAD,
        verbose_name="Tax Currency",
        help_text="Currency for tax calculations"
    )

    # Status and Management
    status = models.CharField(
        max_length=20,
        choices=CarrierStatus.choices,
        default=CarrierStatus.ACTIVE
    )

    is_active = models.BooleanField(default=True, verbose_name="Is Active", help_text="Whether the carrier is active")
    notes = models.TextField(blank=True, verbose_name="Notes", help_text="Notes about the carrier")

    # Tenant relationship
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Carrier"
        verbose_name_plural = "Carriers"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["business_number"]),
            models.Index(fields=["status"])
        ]

    def __str__(self):
        return self.name
    
    # def clean(self):

    def save(self, *args, **kwargs):
        # Update status based on truck assignments
        from dispatch.models import DriverTruckAssignment, AssignmentStatus
        
        # Check if any trucks belonging to this carrier are assigned
        active_assignments = DriverTruckAssignment.objects.filter(
            truck__carrier=self,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
        ).exists()

        if not self.is_active:
            self.status = CarrierStatus.INACTIVE
        elif active_assignments:
            self.status = CarrierStatus.ACTIVE
        else:
            self.status = CarrierStatus.PENDING

        super().save(*args, **kwargs) 