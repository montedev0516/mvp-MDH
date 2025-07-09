from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from models.models import BaseModel
from django.contrib.contenttypes.fields import GenericRelation
from fleet.models import Driver, Truck, Carrier, DutyStatus, TruckDutyStatus
from .status_history import StatusHistory
from .notification import Notification


class AssignmentStatus(models.TextChoices):
    UNASSIGNED = "unassigned", "Unassigned"  # Initial state
    ASSIGNED = "assigned", "Assigned"  # Driver and truck are assigned
    ON_DUTY = "on_duty", "On Duty"  # Assignment is active and in progress
    OFF_DUTY = "off_duty", "Off Duty"  # Assignment is completed
    CANCELLED = "cancelled", "Cancelled"  # Assignment was cancelled


class DriverTruckAssignment(BaseModel):
    """Tracks assignment of drivers to trucks for specific time periods"""

    # Add generic relations for history and notifications
    status_history = GenericRelation('dispatch.StatusHistory')
    notifications = GenericRelation('dispatch.Notification')

    # Core relationship fields
    driver = models.ForeignKey(
        "fleet.Driver",
        on_delete=models.CASCADE,
        related_name="truck_assignments",
        help_text="The driver assigned to the truck"
    )
    truck = models.ForeignKey(
        "fleet.Truck",
        on_delete=models.CASCADE,
        related_name="driver_assignments",
        help_text="The truck assigned to the driver"
    )
    carrier = models.ForeignKey(
        "fleet.Carrier",
        on_delete=models.CASCADE,
        related_name="driver_carrier_assignments",
        help_text="The carrier assigned to the driver",
        null=True,  # Temporarily allow null
        blank=True  # Temporarily allow blank
    )
    tenant = models.ForeignKey(
        "tenant.Tenant", 
        on_delete=models.CASCADE,
        help_text="Associated tenant"
    )
    dispatch = models.ForeignKey(
        "dispatch.Dispatch",
        on_delete=models.CASCADE,
        related_name="assignments",
        null=True,
        blank=True,
        help_text="Associated dispatch if this is a dispatch-specific assignment"
    )

    # Time period for the assignment
    start_date = models.DateTimeField(
        default=timezone.now,
        help_text="When this assignment begins"
    )
    end_date = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When this assignment ends"
    )

    # Odometer readings
    odometer_start = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Starting odometer reading when assignment begins"
    )
    odometer_end = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Ending odometer reading when assignment ends"
    )

    # Assignment metadata
    notes = models.TextField(
        null=True, 
        blank=True,
        help_text="Additional notes about the assignment"
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ASSIGNED,  # Changed default to ASSIGNED
        help_text="Current status of the assignment"
    )
    
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Driver-Truck Assignment"
        verbose_name_plural = "Driver-Truck Assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "truck", "start_date"],
                name="unique_driver_truck_assignment"
            )
        ]

    def __str__(self):
        driver_name = self.driver.get_full_name() if self.driver else "No Driver"
        truck_unit = self.truck.unit if self.truck else "No Truck"
        return f"{driver_name} - {truck_unit} ({self.start_date.strftime('%Y-%m-%d')})"

    def save(self, *args, **kwargs):
        """Override save to ensure proper status handling and validation"""
        if not self.pk:  # New instance
            if not self.status:
                self.status = AssignmentStatus.ASSIGNED
            
            # Ensure driver and truck are set
            if not self.driver_id:
                raise ValidationError("Driver is required")
            if not self.truck_id:
                raise ValidationError("Truck is required")
            
            # Set carrier from driver if not set
            if not self.carrier_id and self.driver.carrier_id:
                self.carrier = self.driver.carrier

        # Call clean to run validation
        self.clean()
        
        # Call super to save
        return super().save(*args, **kwargs)

    def clean(self):
        """Validate the assignment dates and status transitions"""
        if not self.driver_id:
            raise ValidationError("Driver is required")
        if not self.truck_id:
            raise ValidationError("Truck is required")
            
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date")
        
        # Check for overlapping assignments
        overlapping = DriverTruckAssignment.objects.filter(
            driver=self.driver,
            status__in=[AssignmentStatus.ASSIGNED, AssignmentStatus.ON_DUTY]
        ).exclude(id=self.id)
        
        if self.end_date:
            overlapping = overlapping.filter(
                models.Q(start_date__range=(self.start_date, self.end_date)) |
                models.Q(end_date__range=(self.start_date, self.end_date)) |
                models.Q(start_date__lte=self.start_date, end_date__gte=self.end_date)
            )
        else:
            overlapping = overlapping.filter(
                models.Q(start_date__gte=self.start_date) |
                models.Q(end_date__isnull=True)
            )
            
        if overlapping.exists():
            raise ValidationError("Driver has overlapping assignments in this time period")

        # Validate driver availability
        if self.driver.driveremployment.duty_status not in [DutyStatus.AVAILABLE, DutyStatus.ON_DUTY]:
            raise ValidationError("Driver is not available for assignment")

        # Validate truck availability
        if self.truck.duty_status not in [TruckDutyStatus.AVAILABLE, TruckDutyStatus.ON_DUTY]:
            raise ValidationError("Truck is not available for assignment")

    def validate_status_transition(self, new_status):
        """Validate if the status transition is allowed"""
        if not self.status:
            self.status = AssignmentStatus.ASSIGNED
            return True
            
        # Define allowed transitions
        allowed_transitions = {
            AssignmentStatus.UNASSIGNED: [AssignmentStatus.ASSIGNED],
            AssignmentStatus.ASSIGNED: [AssignmentStatus.ON_DUTY, AssignmentStatus.CANCELLED],
            AssignmentStatus.ON_DUTY: [AssignmentStatus.OFF_DUTY],
            AssignmentStatus.OFF_DUTY: [],  # Final state
            AssignmentStatus.CANCELLED: [],  # Final state
        }

        if new_status not in allowed_transitions.get(self.status, []):
            raise ValidationError(
                f"Invalid status transition from {self.get_status_display()} to {dict(AssignmentStatus.choices)[new_status]}"
            )
        return True

    def sync_driver_truck_status(self):
        """Synchronize driver and truck status based on assignment status"""
        with transaction.atomic():
            # Update driver status
            driver_employment = self.driver.driveremployment
            if self.status in [AssignmentStatus.ON_DUTY, AssignmentStatus.ASSIGNED]:
                driver_employment.duty_status = DutyStatus.ON_DUTY
            elif self.status in [AssignmentStatus.OFF_DUTY, AssignmentStatus.CANCELLED]:
                driver_employment.duty_status = DutyStatus.AVAILABLE
            driver_employment.save()

            # Update truck status
            if self.status in [AssignmentStatus.ON_DUTY, AssignmentStatus.ASSIGNED]:
                self.truck.duty_status = TruckDutyStatus.ON_DUTY
            elif self.status in [AssignmentStatus.OFF_DUTY, AssignmentStatus.CANCELLED]:
                self.truck.duty_status = TruckDutyStatus.AVAILABLE
            self.truck.save()

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change and create notification"""
        # Create status history entry
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'driver': str(self.driver),
                'truck': str(self.truck),
                'carrier': str(self.carrier),
                'start_date': self.start_date.isoformat() if self.start_date else None,
                'end_date': self.end_date.isoformat() if self.end_date else None,
            }
        )

        # Create notification with appropriate priority
        priority = 'high' if new_status in [AssignmentStatus.OFF_DUTY, AssignmentStatus.CANCELLED] else 'medium'
        Notification.create_status_change_notification(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            priority=priority
        )



    