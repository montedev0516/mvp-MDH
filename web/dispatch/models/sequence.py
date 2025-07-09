from django.db import models
from django.utils import timezone
from models.models import BaseModel
from django.db import transaction

class SequenceType(models.TextChoices):
    TRIP = "TRIP", "Trip"
    ORDER = "ORDER", "Order"
    DISPATCH = "DISPATCH", "Dispatch"

class TenantSequence(BaseModel):
    """Model to manage sequences for each tenant."""
    
    tenant = models.ForeignKey(
        "tenant.Tenant",
        on_delete=models.CASCADE,
        help_text="Associated tenant"
    )
    sequence_type = models.CharField(
        max_length=50,
        choices=SequenceType.choices,
        default=SequenceType.TRIP,
        help_text="Type of sequence (e.g., TRIP, ORDER, etc.)"
    )
    current_value = models.IntegerField(
        default=0,
        help_text="Current sequence value"
    )
    last_reset = models.DateField(
        default=timezone.now,
        help_text="Date when the sequence was last reset"
    )

    class Meta:
        unique_together = ('tenant', 'sequence_type')
        indexes = [
            models.Index(fields=['tenant', 'sequence_type']),
        ]

    @classmethod
    def get_next_sequence(cls, tenant, sequence_type):
        """
        Get the next sequence number for the given tenant and sequence type.
        Resets daily.
        """
        today = timezone.now().date()
        
        with transaction.atomic():
            sequence, created = cls.objects.select_for_update().get_or_create(
                tenant=tenant,
                sequence_type=sequence_type,
                defaults={'last_reset': today}
            )
            
            # Reset sequence if it's a new day
            if sequence.last_reset != today:
                sequence.current_value = 0
                sequence.last_reset = today
            
            # Increment sequence
            sequence.current_value += 1
            sequence.save()
            
            return sequence.current_value 