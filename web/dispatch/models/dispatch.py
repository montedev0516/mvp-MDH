from django.db import models
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from models.models import BaseModel, Currency
from .drivertruckassignment import AssignmentStatus
from fleet.models import Driver, Truck, Carrier, DutyStatus, TruckDutyStatus
from decimal import Decimal
from .order import OrderStatus
from .trip import TripStatus
from .status_history import StatusHistory
from .notification import Notification
from django.contrib.contenttypes.fields import GenericRelation
from .sequence import TenantSequence, SequenceType
import logging

logger = logging.getLogger(__name__)


class DispatchStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ASSIGNED = "assigned", "Assigned"
    IN_TRANSIT = "in_transit", "In Transit"
    DELIVERED = "delivered", "Delivered"
    INVOICED = "invoiced", "Invoiced"
    PAYMENT_RECEIVED = "payment_received", "Payment Received"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Dispatch(BaseModel):
    # Add generic relations for history and notifications
    status_history = GenericRelation('dispatch.StatusHistory')
    notifications = GenericRelation('dispatch.Notification')

    # Identification
    dispatch_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,  # Allow null initially, will be set in save()
        blank=True
    )
    order_number = models.CharField(max_length=50, null=True, blank=True)
    order_date = models.DateTimeField(null=True, blank=True)

    # Core relationships
    order = models.ForeignKey(
        "dispatch.Order",
        on_delete=models.CASCADE,
        related_name="dispatches",
        help_text="Order being dispatched"
    )
    customer = models.ForeignKey(
        "fleet.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Customer for this dispatch"
    )
    trip = models.ForeignKey(
        "dispatch.Trip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Associated trip details"
    )
    driver = models.ForeignKey(
        "fleet.Driver",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Assigned driver"
    )
    truck = models.ForeignKey(
        "fleet.Truck",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Assigned truck"
    )
    tenant = models.ForeignKey(
        "tenant.Tenant", 
        on_delete=models.CASCADE,
        help_text="Associated tenant"
    )

    # Carrier information
    carrier = models.ForeignKey(
        "fleet.Carrier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Carrier handling this dispatch"
    )

    # Financial details
    commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual commission amount"
    )
    commission_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal('12.0'),
        help_text="Commission percentage"
    )
    commission_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.CAD,
        help_text="Currency for commission amounts"
    )

    # Timing
    # scheduled_start = models.DateTimeField(
    #     null=True,
    #     blank=True,
    #     help_text="Scheduled start time"
    # )
    # scheduled_end = models.DateTimeField(
    #     null=True,
    #     blank=True,
    #     help_text="Scheduled end time"
    # )
    actual_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual start time"
    )
    actual_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual end time"
    )

    # Status and metadata
    status = models.CharField(
        max_length=20,
        choices=DispatchStatus.choices,
        default=DispatchStatus.PENDING,
        help_text="Current status of the dispatch"
    )
    notes = models.TextField(
        null=True,
        blank=True,
        help_text="Additional notes about the dispatch"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
   
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dispatch"
        verbose_name_plural = "Dispatches"

    def __str__(self):
        return f"Dispatch {self.dispatch_id} - {self.get_status_display()}"

    def get_notification_priority(self):
        """Get notification priority based on status"""
        if self.status in ['completed', 'cancelled']:
            return 'high'
        elif self.status in ['in_transit', 'delivered']:
            return 'medium'
        return 'low'

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change and create notification"""
        # Create status history entry
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'dispatch_id': self.dispatch_id,
                'order_number': self.order_number,
                'customer': str(self.customer) if self.customer else None,
            }
        )

        # Create notification with appropriate priority
        priority = 'high' if new_status in ['completed', 'cancelled'] else 'medium'
        Notification.create_status_change_notification(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            priority=priority
        )

    def validate_status_transition(self, new_status):
        """Validate if the status transition is allowed"""
        if self.status == new_status:
            return True

        allowed_transitions = {
            DispatchStatus.PENDING: [DispatchStatus.ASSIGNED, DispatchStatus.CANCELLED],
            DispatchStatus.ASSIGNED: [DispatchStatus.IN_TRANSIT, DispatchStatus.CANCELLED],
            DispatchStatus.IN_TRANSIT: [DispatchStatus.DELIVERED, DispatchStatus.CANCELLED],
            DispatchStatus.DELIVERED: [DispatchStatus.INVOICED, DispatchStatus.CANCELLED],
            DispatchStatus.INVOICED: [DispatchStatus.PAYMENT_RECEIVED, DispatchStatus.CANCELLED],
            DispatchStatus.PAYMENT_RECEIVED: [DispatchStatus.COMPLETED, DispatchStatus.CANCELLED],
            DispatchStatus.COMPLETED: [],  # No transitions allowed from COMPLETED
            DispatchStatus.CANCELLED: [],  # No transitions allowed from CANCELLED
        }

        if new_status not in allowed_transitions.get(self.status, []):
            raise ValidationError(
                f"Invalid status transition from {self.status} to {new_status}"
            )
        return True

    def sync_related_statuses(self, old_status=None, user=None):
        """Synchronize related Order, Trip, and Assignment statuses"""
        with transaction.atomic():
            try:
                # Sync Order status
                if self.order:
                    if self.status in [DispatchStatus.ASSIGNED, DispatchStatus.IN_TRANSIT, DispatchStatus.DELIVERED]:
                        if self.order.status == OrderStatus.PENDING:
                            old_order_status = self.order.status
                            self.order.status = OrderStatus.IN_PROGRESS
                            self.order.save()
                            self.order.log_status_change(old_order_status, OrderStatus.IN_PROGRESS, user)
                    
                    elif self.status == DispatchStatus.COMPLETED:
                        if self.order.status != OrderStatus.COMPLETED:
                            old_order_status = self.order.status
                            self.order.status = OrderStatus.COMPLETED
                            self.order.save()
                            self.order.log_status_change(old_order_status, OrderStatus.COMPLETED, user)
                    
                    elif self.status == DispatchStatus.CANCELLED:
                        if self.order.status != OrderStatus.CANCELLED:
                            old_order_status = self.order.status
                            self.order.status = OrderStatus.CANCELLED
                            self.order.save()
                            self.order.log_status_change(old_order_status, OrderStatus.CANCELLED, user)

                # Sync Trip status
                if self.trip:
                    if self.status == DispatchStatus.IN_TRANSIT:
                        if self.trip.status != TripStatus.IN_PROGRESS:
                            old_trip_status = self.trip.status
                            self.trip.status = TripStatus.IN_PROGRESS
                            self.trip.start_time = timezone.now()
                            self.trip.save()
                            self.trip.log_status_change(old_trip_status, TripStatus.IN_PROGRESS, user)
                    
                    elif self.status == DispatchStatus.DELIVERED:
                        if self.trip.status != TripStatus.COMPLETED:
                            old_trip_status = self.trip.status
                            self.trip.status = TripStatus.COMPLETED
                            self.trip.end_time = timezone.now()
                            self.trip.update_actual_values()
                            self.trip.save()
                            self.trip.log_status_change(old_trip_status, TripStatus.COMPLETED, user)
                    
                    elif self.status == DispatchStatus.CANCELLED:
                        if self.trip.status != TripStatus.CANCELLED:
                            old_trip_status = self.trip.status
                            self.trip.status = TripStatus.CANCELLED
                            self.trip.save()
                            self.trip.log_status_change(old_trip_status, TripStatus.CANCELLED, user)

                # Sync DriverTruckAssignment status
                assignments = self.assignments.filter(is_active=True)
                for assignment in assignments:
                    old_assignment_status = assignment.status
                    
                    if self.status == DispatchStatus.ASSIGNED:
                        if assignment.status != AssignmentStatus.ASSIGNED:
                            assignment.status = AssignmentStatus.ASSIGNED
                            assignment.save()
                            assignment.sync_driver_truck_status()
                            assignment.log_status_change(old_assignment_status, AssignmentStatus.ASSIGNED, user)
                    
                    elif self.status == DispatchStatus.IN_TRANSIT:
                        if assignment.status != AssignmentStatus.ON_DUTY:
                            assignment.status = AssignmentStatus.ON_DUTY
                            assignment.save()
                            assignment.sync_driver_truck_status()
                            assignment.log_status_change(old_assignment_status, AssignmentStatus.ON_DUTY, user)
                    
                    elif self.status in [DispatchStatus.COMPLETED, DispatchStatus.DELIVERED]:
                        if assignment.status != AssignmentStatus.OFF_DUTY:
                            assignment.status = AssignmentStatus.OFF_DUTY
                            # Ensure end_date is not before start_date
                            current_time = timezone.now()
                            if assignment.start_date and current_time < assignment.start_date:
                                # If assignment hasn't started yet, set end_date to start_date
                                assignment.end_date = assignment.start_date
                                logger.warning(
                                    f"Assignment {assignment.id} end_date set to start_date ({assignment.start_date}) "
                                    f"because current time ({current_time}) is before start_date"
                                )
                            else:
                                assignment.end_date = current_time
                            assignment.save()
                            assignment.sync_driver_truck_status()
                            assignment.log_status_change(old_assignment_status, AssignmentStatus.OFF_DUTY, user)
                    
                    elif self.status == DispatchStatus.CANCELLED:
                        if assignment.status != AssignmentStatus.CANCELLED:
                            assignment.status = AssignmentStatus.CANCELLED
                            # Ensure end_date is not before start_date
                            current_time = timezone.now()
                            if assignment.start_date and current_time < assignment.start_date:
                                # If assignment hasn't started yet, set end_date to start_date
                                assignment.end_date = assignment.start_date
                                logger.warning(
                                    f"Assignment {assignment.id} end_date set to start_date ({assignment.start_date}) "
                                    f"because current time ({current_time}) is before start_date"
                                )
                            else:
                                assignment.end_date = current_time
                            assignment.save()
                            assignment.sync_driver_truck_status()
                            assignment.log_status_change(old_assignment_status, AssignmentStatus.CANCELLED, user)

                # Update timing fields
                if self.status == DispatchStatus.IN_TRANSIT and not self.actual_start:
                    self.actual_start = timezone.now()
                elif self.status in [DispatchStatus.DELIVERED, DispatchStatus.COMPLETED] and not self.actual_end:
                    self.actual_end = timezone.now()

            except Exception as e:
                logger.error(f"Error syncing related statuses for dispatch {self.dispatch_id}: {str(e)}")
                raise ValidationError(f"Failed to sync related statuses: {str(e)}")

    def generate_dispatch_id(self):
        """Generate a unique dispatch ID."""
        # Get next sequence number for this tenant
        sequence = TenantSequence.get_next_sequence(self.tenant, SequenceType.DISPATCH)
        
        # Format: DISP-YYYYMMDD-XXXX where XXXX is the sequence number
        date_str = timezone.now().strftime("%Y%m%d")
        return f"DISP-{date_str}-{sequence:04d}"

    def save(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Get user from kwargs if provided
        is_new = not self.pk  # Check if this is a new instance
        
        # Generate dispatch_id for new instances
        if not self.dispatch_id:
            self.dispatch_id = self.generate_dispatch_id()
        
        # Get old instance if it exists
        if not is_new:
            try:
                old_instance = Dispatch.objects.get(pk=self.pk)
                # Validate and handle status transition
                if old_instance.status != self.status:
                    self.validate_status_transition(self.status)
                    self.sync_related_statuses(old_status=old_instance.status, user=user)
            except Dispatch.DoesNotExist:
                pass
        
        # Set order_number and order_date from the associated order
        if self.order:
            if not self.order_number:
                self.order_number = self.order.order_number
            if not self.order_date:
                self.order_date = self.order.order_date or self.order.created_at
        
        super().save(*args, **kwargs)
