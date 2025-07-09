from django.db import models
from django.utils import timezone
from models.models import BaseModel, Currency
from django.contrib.contenttypes.fields import GenericRelation
from .status_history import StatusHistory
from .notification import Notification
from .sequence import TenantSequence, SequenceType
import uuid

class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"

class Order(BaseModel):
    # Add generic relations for history and notifications
    status_history = GenericRelation('dispatch.StatusHistory')
    notifications = GenericRelation('dispatch.Notification')

    # Order fields
    order_number = models.CharField(
        max_length=255,
        unique=True,
        null=True,  # Allow null initially, will be set in save()
        blank=True
    )
    pdf = models.TextField(blank=True, null=True, help_text="PDF representation of the order")
    
    # Customer fields (deprecated - use customer relationship instead)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_address = models.CharField(max_length=255, null=True, blank=True)
    customer_email = models.EmailField(null=True, blank=True)
    customer_phone = models.CharField(max_length=255, null=True, blank=True)
    
    # Customer relationship
    customer = models.ForeignKey(
        "fleet.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Customer associated with this order"
    )
    
    # Shipping details
    origin = models.CharField(
        max_length=255, null=True, blank=True, help_text="Pickup address"
    )
    destination = models.CharField(
        max_length=255, null=True, blank=True, help_text="Delivery address"
    )
    cargo_type = models.CharField(max_length=100, null=True, blank=True)
    weight = models.FloatField(null=True, blank=True, help_text="Weight in pounds/kilograms")
    pickup_date = models.DateTimeField(null=True, blank=True)
    delivery_date = models.DateTimeField(null=True, blank=True)

    # Financial details
    remarks_or_special_instructions = models.TextField(null=True, blank=True)
    load_total = models.FloatField(null=True, blank=True, help_text="Total cost of the load")
    load_currency = models.CharField(max_length=255, null=True, blank=True)

    # AI/LLM Processing fields
    raw_extract = models.JSONField(help_text="Extracted structured data from document processing")
    raw_text = models.TextField(help_text="Original text extracted from documents")
    completion_tokens = models.IntegerField(help_text="Number of tokens in the completion")
    prompt_tokens = models.IntegerField(help_text="Number of tokens in the prompt")
    total_tokens = models.IntegerField(help_text="Total tokens used in processing")
    llm_model_name = models.CharField(max_length=255, help_text="Name of the LLM model used")
    usage_details = models.JSONField(help_text="Detailed usage information from AI processing")
    processed = models.BooleanField(default=False, help_text="Whether the order has been processed by AI")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Relationships
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)

    # Status fields
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, 
        choices=OrderStatus.choices, 
        default=OrderStatus.PENDING
    )
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return self.order_number

    @property
    def current_dispatch(self):
        """Get the current active dispatch for this order"""
        return self.dispatches.filter(is_active=True).first()

    @property
    def current_trip(self):
        """Get the current active trip for this order"""
        return self.trips.filter(is_active=True).first()

    def validate_status_transition(self, new_status):
        """
        Validate if the status transition is allowed
        """
        if self.status == new_status:
            return True

        # Define allowed transitions
        allowed_transitions = {
            OrderStatus.PENDING: [OrderStatus.IN_PROGRESS, OrderStatus.CANCELLED],
            OrderStatus.IN_PROGRESS: [OrderStatus.COMPLETED, OrderStatus.CANCELLED],
            OrderStatus.COMPLETED: [],  # No transitions allowed from COMPLETED
            OrderStatus.CANCELLED: [],  # No transitions allowed from CANCELLED
        }

        if new_status not in allowed_transitions.get(self.status, []):
            raise ValueError(
                f"Invalid status transition from {self.status} to {new_status}"
            )
        return True

    def generate_order_number(self):
        """Generate a unique order number."""
        # Get next sequence number for this tenant
        sequence = TenantSequence.get_next_sequence(self.tenant, SequenceType.ORDER)
        
        # Format: ORD-YYYYMMDD-XXXX where XXXX is the sequence number
        date_str = timezone.now().strftime("%Y%m%d")
        return f"ORD-{date_str}-{sequence:04d}"

    def save(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # Get user from kwargs if provided
        is_new = not self.pk  # Check if this is a new instance
        
        # Generate order number for new instances
        if not self.order_number:
            self.order_number = self.generate_order_number()
        
        if not is_new:
            try:
                old_instance = Order.objects.get(pk=self.pk)
                # Validate and handle status transition
                if old_instance.status != self.status:
                    self.validate_status_transition(self.status)
            except Order.DoesNotExist:
                # Handle the case where the instance doesn't exist yet
                pass
        
        super().save(*args, **kwargs)

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change and create notification"""
        # Create status history entry
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'order_number': self.order_number,
                'customer': str(self.customer) if self.customer else None,
            }
        )

        # Create notification with appropriate priority
        priority = 'high' if new_status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED] else 'medium'
        Notification.create_status_change_notification(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            priority=priority
        )