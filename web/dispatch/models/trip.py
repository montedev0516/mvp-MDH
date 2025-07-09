from django.db import models
from models.models import BaseModel, Currency
from django.utils import timezone
from .order import OrderStatus
from django.contrib.contenttypes.fields import GenericRelation
from .status_history import StatusHistory
from .notification import Notification
from django.contrib.contenttypes.models import ContentType
from .sequence import TenantSequence, SequenceType
import logging

logger = logging.getLogger(__name__)


class TripStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Trip(BaseModel):
    # Add generic relations for history and notifications
    status_history = GenericRelation('dispatch.StatusHistory')
    notifications = GenericRelation('dispatch.Notification')

    # Trip identification
    trip_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,  # Allow null initially, will be set in save()
        blank=True,
        help_text="Unique trip identifier"
    )

    # Relationships
    order = models.ForeignKey(
        "dispatch.Order", 
        on_delete=models.CASCADE,
        related_name="trips",
        help_text="Order associated with this trip"
    )
    tenant = models.ForeignKey(
        "tenant.Tenant", 
        on_delete=models.CASCADE
    )

    # Trip planning details
    estimated_distance = models.FloatField(
        null=True, blank=True, 
        help_text="Estimated trip distance in miles/km"
    )
    estimated_duration = models.DurationField(
        null=True, blank=True, 
        help_text="Estimated trip duration"
    )
    actual_distance = models.FloatField(
        null=True, blank=True,
        help_text="Actual distance traveled"
    )
    actual_duration = models.DurationField(
        null=True, blank=True,
        help_text="Actual trip duration"
    )
    route = models.JSONField(
        null=True, blank=True, 
        help_text="JSON data containing the route information"
    )
    stops = models.JSONField(
        null=True, blank=True, 
        help_text="JSON data containing stops along the route"
    )

    # Cost tracking
    fuel_estimated = models.FloatField(
        null=True, blank=True, 
        help_text="Estimated fuel cost"
    )
    fuel_actual = models.FloatField(
        null=True, blank=True,
        help_text="Actual fuel cost"
    )
    toll_estimated = models.FloatField(
        null=True, blank=True, 
        help_text="Estimated toll cost"
    )
    toll_actual = models.FloatField(
        null=True, blank=True,
        help_text="Actual toll cost"
    )
    freight_estimated = models.FloatField(
        null=True, blank=True, 
        help_text="Estimated freight value"
    )
    freight_actual = models.FloatField(
        null=True, blank=True,
        help_text="Actual freight value"
    )

    # Financial details
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.CAD,
        help_text="Currency for all monetary values"
    )

    # Timing
    start_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Actual trip start time"
    )
    end_time = models.DateTimeField(
        null=True, blank=True,
        help_text="Actual trip end time"
    )

    # Status and metadata
    status = models.CharField(
        max_length=20, 
        choices=TripStatus.choices, 
        default=TripStatus.PENDING
    )
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # New fields
    freight_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Value of the freight being transported"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Trip"
        verbose_name_plural = "Trips"

    def __str__(self):
        return f"Trip {self.trip_id}"

    @property
    def current_dispatch(self):
        """Get the current dispatch associated with this trip"""
        return self.dispatch_set.filter(is_active=True).first()

    def get_status_color(self):
        """Get the appropriate color for the status badge."""
        status_colors = {
            TripStatus.PENDING: "secondary",
            TripStatus.IN_PROGRESS: "primary",
            TripStatus.COMPLETED: "success",
            TripStatus.CANCELLED: "danger"
        }
        return status_colors.get(self.status, "secondary")

    def validate_status_transition(self, new_status):
        """
        Validate if the status transition is allowed
        """
        # If this is a new trip (no current status), only allow PENDING
        if not self.status or self.status is None:
            if new_status != TripStatus.PENDING:
                raise ValueError(f"New trips must have status {TripStatus.PENDING}")
            return True

        # For existing trips, check the transition
        if self.status == new_status:
            return True

        # Define allowed transitions
        allowed_transitions = {
            TripStatus.PENDING: [TripStatus.IN_PROGRESS, TripStatus.CANCELLED],
            TripStatus.IN_PROGRESS: [TripStatus.COMPLETED, TripStatus.CANCELLED],
            TripStatus.COMPLETED: [],  # No transitions allowed from COMPLETED
            TripStatus.CANCELLED: [],  # No transitions allowed from CANCELLED
        }

        if new_status not in allowed_transitions.get(self.status, []):
            raise ValueError(
                f"Invalid status transition from {self.status} to {new_status}"
            )
        return True

    def update_actual_values(self):
        """Update actual distance, duration and costs if trip is completed"""
        if self.status == TripStatus.COMPLETED and not self.end_time:
            self.end_time = timezone.now()
            
            if self.start_time:
                self.actual_duration = self.end_time - self.start_time
                
            # Here you could add logic to calculate actual distance and costs
            # based on GPS tracking or other data sources

    def generate_trip_id(self):
        """Generate a unique trip ID."""
        # Get next sequence number for this tenant
        sequence = TenantSequence.get_next_sequence(self.tenant, SequenceType.TRIP)
        
        # Format: TRIP-YYYYMMDD-XXXX where XXXX is the sequence number
        date_str = timezone.now().strftime("%Y%m%d")
        return f"TRIP-{date_str}-{sequence:04d}"

    def save(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Get user from kwargs if provided
        
        # Generate trip_id for new instances
        if not self.trip_id:
            self.trip_id = self.generate_trip_id()
        
        # Ensure status is set
        if not self.status or self.status is None:
            self.status = TripStatus.PENDING
            logger.info(f"Setting default status to {self.status}")
        
        # Get old instance if it exists
        if self.pk:
            try:
                old_instance = Trip.objects.get(pk=self.pk)
                # Validate and handle status transition
                if old_instance.status != self.status:
                    self.validate_status_transition(self.status)
                    
                    # If moving to IN_PROGRESS and no start time
                    if self.status == TripStatus.IN_PROGRESS and not self.start_time:
                        self.start_time = timezone.now()
                    
                    # If completing or cancelling, update actual values
                    if self.status in [TripStatus.COMPLETED, TripStatus.CANCELLED]:
                        self.update_actual_values()
                    
                    super().save(*args, **kwargs)
                    self.log_status_change(old_instance.status, self.status, user)
                else:
                    super().save(*args, **kwargs)
            except Trip.DoesNotExist:
                # This is a new instance being saved with a PK
                super().save(*args, **kwargs)
                self.log_status_change(None, self.status, user)
        else:
            # New instance
            super().save(*args, **kwargs)
            # Log initial status
            self.log_status_change(None, self.status, user)

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change to status history"""
        from dispatch.models import StatusHistory
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'trip_id': self.trip_id,
                'order_number': self.order.order_number if self.order else None,
            }
        )

    def delete(self, *args, **kwargs):
        """Override delete to clean up notifications and status history before deleting the trip."""
        # Get content type for this model
        content_type = ContentType.objects.get_for_model(self)
        
        # Delete related notifications and status history
        Notification.objects.filter(
            content_type=content_type,
            object_id=str(self.id)  # Convert UUID to string for comparison
        ).delete()
        
        StatusHistory.objects.filter(
            content_type=content_type,
            object_id=self.id  # UUIDField can handle UUID directly
        ).delete()
        
        # Proceed with normal deletion
        return super().delete(*args, **kwargs)