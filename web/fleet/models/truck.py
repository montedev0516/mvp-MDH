from django.db import models
from models.models import BaseModel
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation

class TruckStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    MAINTENANCE = "maintenance", "Maintenance"
    RETIRED = "retired", "Retired"

class OwnershipType(models.TextChoices):
    OWNED = "owned", "Owned"
    RENTED = "rented", "Rented"
    LEASED = "leased", "Leased"

class TruckType(models.TextChoices):
    TRACTOR = "tractor", "Tractor"
    STRAIGHT_TRUCK = "straight_truck", "Straight Truck"
    BOX_TRUCK = "box_truck", "Box Truck"
    DUMP_TRUCK = "dump_truck", "Dump Truck"
    FLATBED_TRUCK = "flatbed_truck", "Flatbed Truck"

class TruckDutyStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    ON_DUTY = "on_duty", "On Duty"
    OFF_DUTY = "off_duty", "Off Duty"
    IN_MAINTENANCE = "in_maintenance", "In Maintenance"
    OUT_OF_SERVICE = "out_of_service", "Out of Service"


class Truck(BaseModel):
    """Truck model"""
    # Core Information
    unit = models.IntegerField(
        unique=True, 
        verbose_name="Unit Number", 
        help_text="The unique number of the truck")
    plate = models.CharField(
        max_length=20, 
        verbose_name="License Plate", 
        help_text="The license plate of the truck")
    vin = models.CharField(
        max_length=17,
        null=True, blank=True,
        verbose_name="VIN Number", 
        help_text="The Vehicle Identification Number of the truck")
    status_history = GenericRelation('dispatch.StatusHistory')
    
    # Basic Information
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    value = models.FloatField(
        null=True, blank=True,
        verbose_name="Value", 
        help_text="The value of the truck")
    
    year = models.IntegerField(
        verbose_name="Year", 
        help_text="The year of the truck")
    country = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Country", 
        help_text="The country of the truck")
    state = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="State", 
        help_text="The state of the truck")
    registration = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Registration", 
        help_text="The registration of the truck")
    ownership_type = models.CharField(
        max_length=50, 
        verbose_name="Ownership Type", 
        choices=OwnershipType.choices,
        default=OwnershipType.OWNED,
        help_text="The ownership type of the truck")
    tracking = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Tracking", 
        help_text="The tracking of the truck")
    leave_date = models.DateTimeField(
        null=True, 
        blank=True, 
        verbose_name="Leave Date", 
        help_text="The date the truck left the fleet")
    still_working = models.BooleanField(
        default=True, 
        verbose_name="Still Working", 
        help_text="Whether the truck is still working")
    is_trailer = models.BooleanField(
        default=False, 
        verbose_name="Is Trailer", 
        help_text="Whether the truck is a trailer")
    trailer_number = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Trailer Number", 
        help_text="The trailer number of the truck")
    trailer_capacity = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Trailer Capacity",    
        help_text="The capacity of the trailer")
    
    # Fuel Information
    company_pays_fuel_cost = models.BooleanField(
        default=True, 
        verbose_name="Company Pays Fuel Cost", 
        help_text="Whether the company pays the fuel cost")
    all_fuel_toll_cards = models.BooleanField(
        default=True, 
        verbose_name="All Fuel Toll Cards", 
        help_text="Whether the truck has all fuel toll cards")
    ifta_group = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="IFTA Group", 
        help_text="The IFTA group of the truck")
    terminal = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Terminal",    
        help_text="The terminal of the truck")
    tour = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Tour",    
        help_text="The tour of the truck")
    
    
    # Physical Information
    weight = models.FloatField(
        null=True, blank=True,
        verbose_name="Weight", 
        help_text="The weight of the truck")
    capacity = models.CharField(
        max_length=50,
        null=True, blank=True,
        verbose_name="Capacity",    
        help_text="The capacity of the truck")

    # Status Information
    status = models.CharField(
        max_length=20,
        choices=TruckStatus.choices,
        default=TruckStatus.ACTIVE,
        verbose_name="Status",
        help_text="The status of the truck")

    duty_status = models.CharField(
        max_length=20,
        choices=TruckDutyStatus.choices,
        default=TruckDutyStatus.AVAILABLE,
        verbose_name="Duty Status",
        help_text="The current duty status of the truck"
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active",
        help_text="Whether the truck is active")
    notes = models.TextField(blank=True)
    
    # Carrier Information
    carrier = models.ForeignKey(
        "fleet.Carrier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trucks"
    )

    # Tenant Information
    tenant = models.ForeignKey(
        "tenant.Tenant",
        on_delete=models.CASCADE,
        related_name="trucks"
    )

    class Meta:
        ordering = ["unit"]
        verbose_name = "Truck"
        verbose_name_plural = "Trucks"

    def __str__(self):
        return f"{self.unit} - {self.make} {self.model} ({self.get_status_display()})"

    def get_current_status(self, check_date=None):
        """
        Get the current status of the truck based on active assignments
        """
        if check_date is None:
            check_date = timezone.now()

        if self.status == TruckStatus.ACTIVE:
            return "Active"
        elif self.status == TruckStatus.INACTIVE:
            return "Inactive"
        elif self.status == TruckStatus.MAINTENANCE:
            return "Maintenance"
        elif self.status == TruckStatus.RETIRED:
            return "Retired"
        else:
            return "Unknown"
        
    def is_available(self, start_date, end_date):       
        if self.status != TruckStatus.ACTIVE:
            return False
        
        if self.leave_date and self.leave_date > start_date:
            return False
        
        return True
    
    def save(self, *args, **kwargs):
        if self.is_trailer:
            self.trailer_number = self.unit
            self.trailer_capacity = self.capacity
        super().save(*args, **kwargs)

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change to status history"""
        from dispatch.models import StatusHistory
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'unit': str(self.unit),
                'make': self.make,
                'model': self.model,
                'status': self.status,
            }
        )