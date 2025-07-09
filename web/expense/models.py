from django.db import models, transaction # type: ignore
from django.utils import timezone # type: ignore
from datetime import timedelta
from django.core.validators import MinValueValidator
from models.models import BaseModel, Currency
from dispatch.models import Trip, TripStatus
from django.core.exceptions import ValidationError
import logging
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)


class AccountPayableStatus(models.TextChoices):
    """
    Status for tracking expenses through accounting workflow:
    - PENDING: Expense recorded but not yet reviewed/approved
    - ACCOUNTED: Expense reviewed and approved for inclusion in payouts
    - PAID: Expense has been paid to driver (included in completed payout)
    """
    PENDING = "Pending", "Pending"
    ACCOUNTED = "Accounted", "Accounted" 
    PAID = "Paid", "Paid"
    
    @classmethod
    def get_status_color(cls, status):
        """Get Bootstrap color class for status badges"""
        color_map = {
            cls.PENDING: "warning",
            cls.ACCOUNTED: "success", 
            cls.PAID: "info"
        }
        return color_map.get(status, "secondary")
    
    @classmethod
    def get_next_statuses(cls, current_status):
        """Get valid next statuses for workflow"""
        transitions = {
            cls.PENDING: [cls.ACCOUNTED],
            cls.ACCOUNTED: [cls.PAID],
            cls.PAID: []  # Final status
        }
        return transitions.get(current_status, [])
    
    @classmethod
    def can_transition(cls, from_status, to_status):
        """Check if status transition is valid"""
        return to_status in cls.get_next_statuses(from_status)


class ReimbursementStatus(models.TextChoices):
    """
    Status for tracking driver reimbursement workflow:
    - PENDING: Awaiting approval
    - APPROVED: Approved for reimbursement
    - REJECTED: Rejected, not eligible for reimbursement
    - PAID: Reimbursement paid to driver
    """
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected" 
    PAID = "PAID", "Paid"
    
    @classmethod
    def get_status_color(cls, status):
        """Get Bootstrap color class for status badges"""
        color_map = {
            cls.PENDING: "warning",
            cls.APPROVED: "info",
            cls.REJECTED: "danger",
            cls.PAID: "success"
        }
        return color_map.get(status, "secondary")
    
    @classmethod
    def get_next_statuses(cls, current_status):
        """Get valid next statuses for workflow"""
        transitions = {
            cls.PENDING: [cls.APPROVED, cls.REJECTED],
            cls.APPROVED: [cls.PAID, cls.REJECTED],
            cls.REJECTED: [cls.PENDING],  # Can be re-submitted
            cls.PAID: []  # Final status
        }
        return transitions.get(current_status, [])


class PayoutStatus(models.TextChoices):
    """
    Status for tracking payout processing workflow:
    - DRAFT: Calculation done, not yet finalized
    - PROCESSING: Being processed for payment
    - COMPLETED: Payment completed and invoices generated
    - CANCELLED: Payout cancelled
    """
    DRAFT = "Draft", "Draft"  # Initial calculation done
    PROCESSING = "Processing", "Processing"  # Invoice generation in progress
    COMPLETED = "Completed", "Completed"  # Invoice generated
    CANCELLED = "Cancelled", "Cancelled"  # Payout cancelled
    
    @classmethod
    def get_status_color(cls, status):
        """Get Bootstrap color class for status badges"""
        color_map = {
            cls.DRAFT: "secondary",
            cls.PROCESSING: "warning", 
            cls.COMPLETED: "success",
            cls.CANCELLED: "danger"
        }
        return color_map.get(status, "secondary")
    
    @classmethod
    def get_next_statuses(cls, current_status):
        """Get valid next statuses for workflow"""
        transitions = {
            cls.DRAFT: [cls.PROCESSING, cls.CANCELLED],
            cls.PROCESSING: [cls.COMPLETED, cls.CANCELLED],
            cls.COMPLETED: [],  # Final status
            cls.CANCELLED: [cls.DRAFT]  # Can be reactivated
        }
        return transitions.get(current_status, [])


class BaseExpense(BaseModel):
    """Base class for all expenses"""
    date = models.DateTimeField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.CAD)
    driver = models.ForeignKey("fleet.Driver", on_delete=models.CASCADE)
    truck = models.ForeignKey("fleet.Truck", on_delete=models.CASCADE)
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=AccountPayableStatus.choices,
        default=AccountPayableStatus.PENDING,
    )

    class Meta:
        abstract = True

    def clean(self):
        """Validate base expense fields"""
        super().clean()
        
        # Validate amount is positive
        if self.amount is not None and self.amount <= 0:
            raise ValidationError("Amount must be greater than 0")
            
        # Validate required fields
        if not self.date:
            raise ValidationError("Date is required")
        if not self.currency:
            raise ValidationError("Currency is required")
        if not self.driver_id:
            raise ValidationError("Driver is required")
        if not self.truck_id:
            raise ValidationError("Truck is required")
        if not self.tenant_id:
            raise ValidationError("Tenant is required")
    
    def get_status_color(self):
        """Get Bootstrap color class for status badge"""
        return AccountPayableStatus.get_status_color(self.status)
    
    def can_change_status_to(self, new_status):
        """Check if status can be changed to new_status"""
        return AccountPayableStatus.can_transition(self.status, new_status)
    
    def get_next_status_options(self):
        """Get list of valid next statuses"""
        return AccountPayableStatus.get_next_statuses(self.status)
    
    def update_status(self, new_status, user=None, system_initiated=False):
        """Update status with validation
        
        Args:
            new_status: The target status
            user: User making the change (for audit trail)
            system_initiated: If True, allows certain automatic transitions (e.g., payout completion)
        """
        # For system-initiated changes (like payout completion), allow more flexible transitions
        if not system_initiated and not self.can_change_status_to(new_status):
            raise ValidationError(
                f"Cannot change status from {self.get_status_display()} to {dict(AccountPayableStatus.choices)[new_status]}"
            )
        
        old_status = self.status
        self.status = new_status
        self.save()
        
        # Log status change
        change_type = "system" if system_initiated else "user"
        logger.info(
            f"Expense {self.pk} status changed from {old_status} to {new_status} by {user} ({change_type})"
        )
        
        return True

class BVD(BaseExpense):
    """Fuel expense model for BVD (Bulk Vehicle Data) records"""
    # Basic info
    company_name = models.CharField(max_length=255)
    card_number = models.CharField(max_length=255)
    time = models.CharField(max_length=255)
    auth_code = models.CharField(max_length=255)
    
    # Vehicle info - 'unit' is the truck unit number for lookup
    unit = models.IntegerField(help_text="Truck unit number from CSV")
    odometer = models.IntegerField(default=0)
    
    # Fuel details
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    uom = models.CharField(max_length=50, default='L', help_text="Unit of measurement (L, GAL)")
    retail_ppu = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(0)])
    billed_ppu = models.DecimalField(max_digits=10, decimal_places=4, validators=[MinValueValidator(0)])
    pre_tax_amt = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Tax info
    pst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    qst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Station info (can be normalized later)
    site_number = models.CharField(max_length=255)
    site_name = models.CharField(max_length=255)
    site_city = models.CharField(max_length=255)
    prov_st = models.CharField(max_length=255)
    
    # Import tracking fields
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    import_batch = models.CharField(max_length=255, null=True, blank=True)
    original_date = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = [
            ("tenant", "date", "card_number", "auth_code", "amount"),
            ("tenant", "date", "unit", "site_number", "quantity"),
        ]
        indexes = [
            models.Index(fields=["tenant", "date", "card_number"]),
            models.Index(fields=["tenant", "date", "unit"]),
            models.Index(fields=["tenant", "auth_code"]),
            models.Index(fields=["unit", "date"]),
        ]

    def clean(self):
        """Validate BVD record"""
        # Call parent validation
        super().clean()
        
        # Skip validation if tenant or date is not set
        if not hasattr(self, 'tenant') or self.tenant is None or not self.date:
            logger.warning("Skipping validation - missing tenant or date")
            return
            
        # Check for duplicates within time window
        time_window = timedelta(minutes=5)
        potential_duplicates = BVD.objects.filter(
            tenant=self.tenant,
            date__range=(self.date - time_window, self.date + time_window),
            unit=self.unit,
            amount=self.amount,
        ).exclude(pk=self.pk)
        
        if potential_duplicates.exists():
            logger.warning(f"Found duplicate BVD records: {[str(d) for d in potential_duplicates]}")
            raise ValidationError(
                "A similar transaction exists within 5 minutes of this one. "
                "Please verify this is not a duplicate."
            )
    
    def __str__(self) -> str:
        return f"BVD {self.unit} - {self.date.strftime('%Y-%m-%d')} - {self.amount} {self.currency}"


class OtherExpense(BaseExpense):
    """Model for non-fuel expenses"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=100,
        choices=[
            ("MAINTENANCE", "Maintenance"),
            ("REPAIR", "Repair"),
            ("TOLL", "Toll"),
            ("PARKING", "Parking"),
            ("INSURANCE", "Insurance"),
            ("LICENSE", "License"),
            ("PERMIT", "Permit"),
            ("SUPPLIES", "Supplies"),
            ("OTHER", "Other"),
        ],
        default="OTHER",
    )
    receipt_image = models.ImageField(upload_to='expense_receipts/%Y/%m/%d/', null=True, blank=True)
    receipt_number = models.CharField(max_length=100, blank=True)
    vendor_name = models.CharField(max_length=255, blank=True)
    vendor_location = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_type = models.CharField(
        max_length=50,
        choices=[
            ("GST", "GST"),
            ("HST", "HST"),
            ("PST", "PST"),
            ("QST", "QST"),
            ("NONE", "None"),
        ],
        default="NONE",
    )
    is_reimbursable = models.BooleanField(default=True)
    reimbursement_status = models.CharField(
        max_length=20,
        choices=ReimbursementStatus.choices,
        default=ReimbursementStatus.PENDING,
    )
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ("CASH", "Cash"),
            ("CREDIT_CARD", "Credit Card"),
            ("DEBIT_CARD", "Debit Card"),
            ("CHEQUE", "Cheque"),
            ("WIRE", "Wire Transfer"),
            ("OTHER", "Other"),
        ],
        default="CASH",
    )
    payment_reference = models.CharField(max_length=255, blank=True)
    odometer = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["-date"]),
            models.Index(fields=["category"]),
            models.Index(fields=["status"]),
            models.Index(fields=["reimbursement_status"]),
        ]

    def __str__(self):
        return f"{self.date} | {self.name} | {self.amount} {self.currency}"

    def clean(self):
        """Additional validation specific to OtherExpense"""
        super().clean()  # This handles amount > 0 and other base validations
        
        # Only OtherExpense-specific validations here
        if self.tax_amount < 0:
            raise ValidationError("Tax amount cannot be negative")
    
    def get_reimbursement_status_color(self):
        """Get Bootstrap color class for reimbursement status badge"""
        return ReimbursementStatus.get_status_color(self.reimbursement_status)
    
    def can_change_reimbursement_status_to(self, new_status):
        """Check if reimbursement status can be changed to new_status"""
        return new_status in ReimbursementStatus.get_next_statuses(self.reimbursement_status)
    
    def get_next_reimbursement_status_options(self):
        """Get list of valid next reimbursement statuses"""
        return ReimbursementStatus.get_next_statuses(self.reimbursement_status)
    
    def update_reimbursement_status(self, new_status, user=None, system_initiated=False):
        """Update reimbursement status with validation
        
        Args:
            new_status: The target reimbursement status
            user: User making the change (for audit trail)
            system_initiated: If True, allows certain automatic transitions (e.g., payout completion)
        """
        # For system-initiated changes, allow more flexible transitions
        if not system_initiated and not self.can_change_reimbursement_status_to(new_status):
            raise ValidationError(
                f"Cannot change reimbursement status from {self.get_reimbursement_status_display()} to {dict(ReimbursementStatus.choices)[new_status]}"
            )
        
        old_status = self.reimbursement_status
        self.reimbursement_status = new_status
        self.save()
        
        # Log status change
        change_type = "system" if system_initiated else "user"
        logger.info(
            f"Expense {self.pk} reimbursement status changed from {old_status} to {new_status} by {user} ({change_type})"
        )
        
        return True


class Payout(BaseModel):
    """Driver payout model for monthly payment calculations"""
    # Date range for payout calculation
    from_date = models.DateTimeField(
        help_text="Start date of payout period"
    )
    to_date = models.DateTimeField(
        help_text="End date of payout period"
    )
    
    # CAD amounts
    cad_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Revenue in CAD"
    )
    cad_commission = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Commission in CAD"
    )
    cad_expenses = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total expenses in CAD (BVD + Other)"
    )
    cad_payout = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Net payout in CAD (revenue - commission - expenses)"
    )
    
    # USD amounts
    usd_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Revenue in USD"
    )
    usd_commission = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Commission in USD"
    )
    usd_expenses = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total expenses in USD (BVD + Other)"
    )
    usd_payout = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Net payout in USD (revenue - commission - expenses)"
    )
    
    # Final calculated amounts
    final_cad_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total amount in CAD after currency conversion"
    )
    final_usd_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total amount in USD after currency conversion"
    )
    
    # Exchange rate used for conversion
    exchange_rate = models.DecimalField(
        max_digits=10, decimal_places=4, default=1,
        help_text="Exchange rate CAD/USD used for conversion"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=PayoutStatus.choices,
        default=PayoutStatus.DRAFT,
        help_text="Payout processing status"
    )
    
    # Relationships
    driver = models.ForeignKey(
        "fleet.Driver", 
        on_delete=models.CASCADE,
        help_text="Driver receiving the payout"
    )
    tenant = models.ForeignKey(
        "tenant.Tenant", 
        on_delete=models.CASCADE,
        help_text="Tenant owning this payout"
    )
    
    # Related expenses (for reference)
    bvd_expenses = models.ManyToManyField(
        BVD, 
        blank=True,
        help_text="BVD expenses included in this payout"
    )
    other_expenses = models.ManyToManyField(
        OtherExpense, 
        blank=True,
        help_text="Other expenses included in this payout"
    )
    
    class Meta:
        unique_together = [
            ("tenant", "driver", "from_date", "to_date"),
        ]
        indexes = [
            models.Index(fields=["tenant", "driver", "from_date"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["from_date", "to_date"]),
        ]
        ordering = ["-from_date"]

    def __str__(self):
        return f"Payout {self.driver} ({self.from_date.strftime('%Y-%m-%d')} to {self.to_date.strftime('%Y-%m-%d')})"
    
    def clean(self):
        """Validate payout data"""
        super().clean()
        
        if self.from_date and self.to_date and self.from_date >= self.to_date:
            raise ValidationError("From date must be before to date")
    
    def get_status_color(self):
        """Get Bootstrap color class for status badge"""
        return PayoutStatus.get_status_color(self.status)
    
    def can_change_status_to(self, new_status):
        """Check if status can be changed to new_status"""
        return new_status in PayoutStatus.get_next_statuses(self.status)
    
    def get_next_status_options(self):
        """Get list of valid next statuses"""
        return PayoutStatus.get_next_statuses(self.status)
    
    def update_status(self, new_status, user=None, system_initiated=False):
        """Update status with validation and business logic"""
        if not system_initiated and not self.can_change_status_to(new_status):
            raise ValidationError(
                f"Cannot change status from {self.get_status_display()} to {dict(PayoutStatus.choices)[new_status]}"
            )
        
        old_status = self.status
        self.status = new_status
        
        # Business logic for status changes
        if new_status == PayoutStatus.COMPLETED:
            # Mark related expenses as PAID
            self._mark_expenses_as_paid()
        elif new_status == PayoutStatus.CANCELLED and old_status == PayoutStatus.PROCESSING:
            # When cancelling a processing payout, we should log this but expenses stay in their current state
            # This is because the expenses may have been processed elsewhere or need manual review
            logger.info(f"Payout {self.pk} cancelled from PROCESSING - expenses remain in current state for manual review")
        
        self.save()
        
        # Log status change
        change_type = "system" if system_initiated else "user"
        logger.info(
            f"Payout {self.pk} status changed from {old_status} to {new_status} by {user} ({change_type})"
        )
        
        return True
    
    def _mark_expenses_as_paid(self):
        """Mark all related expenses as PAID when payout is completed"""
        # Update BVD expenses - mark ALL related expenses as PAID
        # (both PENDING and ACCOUNTED since they were included in payout calculation)
        bvd_expenses = self.bvd_expenses.filter(
            status__in=[AccountPayableStatus.PENDING, AccountPayableStatus.ACCOUNTED]
        )
        
        bvd_count = 0
        for expense in bvd_expenses:
            try:
                expense.update_status(AccountPayableStatus.PAID, user=None, system_initiated=True)
                bvd_count += 1
            except Exception as e:
                logger.error(f"Failed to update BVD expense {expense.pk} status: {str(e)}")
        
        # Update Other expenses (both status and reimbursement_status)
        # Include both PENDING and ACCOUNTED expenses
        other_expenses = self.other_expenses.filter(
            status__in=[AccountPayableStatus.PENDING, AccountPayableStatus.ACCOUNTED]
        )
        
        other_count = 0
        for expense in other_expenses:
            try:
                # Update main status
                expense.update_status(AccountPayableStatus.PAID, user=None, system_initiated=True)
                
                # Also update reimbursement status if it was pending or approved
                if expense.reimbursement_status in [ReimbursementStatus.PENDING, ReimbursementStatus.APPROVED]:
                    expense.update_reimbursement_status(ReimbursementStatus.PAID, user=None, system_initiated=True)
                
                other_count += 1
            except Exception as e:
                logger.error(f"Failed to update Other expense {expense.pk} status: {str(e)}")
            
        # Log the status changes for audit trail
        logger.info(
            f"Payout {self.pk} completion: marked {bvd_count} BVD expenses and {other_count} other expenses as PAID"
        )
    
    def calculate_totals(self, preview_mode=False):
        """Calculate payout totals based on trips and expenses in the date range
        
        Args:
            preview_mode (bool): If True, skip ManyToMany relationship setting for preview calculations
        """
        from dispatch.models import Dispatch, Trip
        
        if not self.driver or not self.from_date or not self.to_date:
            return
            
        # Get all completed dispatches for this driver in the date range
        dispatches = Dispatch.objects.filter(
            driver=self.driver,
            tenant=self.tenant,
            status__in=['completed', 'delivered', 'invoiced', 'payment_received'],
            actual_end__range=[self.from_date, self.to_date]
        ).select_related('trip', 'order')
        
        # Calculate revenue and commission by currency
        cad_revenue = Decimal('0.00')
        usd_revenue = Decimal('0.00')
        cad_commission = Decimal('0.00')
        usd_commission = Decimal('0.00')
        
        for dispatch in dispatches:
            if dispatch.trip and dispatch.trip.freight_value:
                freight_value = Decimal(str(dispatch.trip.freight_value))
                commission = Decimal(str(dispatch.commission_amount or 0))
                
                if dispatch.trip.currency == 'CAD':
                    cad_revenue += freight_value
                    cad_commission += commission
                elif dispatch.trip.currency == 'USD':
                    usd_revenue += freight_value
                    usd_commission += commission
        
        # Calculate expenses by currency
        cad_expenses = Decimal('0.00')
        usd_expenses = Decimal('0.00')
        
        # BVD expenses
        bvd_expenses = BVD.objects.filter(
            driver=self.driver,
            tenant=self.tenant,
            date__range=[self.from_date, self.to_date],
            status__in=[AccountPayableStatus.PENDING, AccountPayableStatus.ACCOUNTED]
        )
        
        for expense in bvd_expenses:
            if expense.currency == 'CAD':
                cad_expenses += expense.amount
            elif expense.currency == 'USD':
                usd_expenses += expense.amount
        
        # Other expenses
        other_expenses = OtherExpense.objects.filter(
            driver=self.driver,
            tenant=self.tenant,
            date__range=[self.from_date, self.to_date],
            status__in=[AccountPayableStatus.PENDING, AccountPayableStatus.ACCOUNTED]
        )
        
        for expense in other_expenses:
            if expense.currency == 'CAD':
                cad_expenses += expense.amount
            elif expense.currency == 'USD':
                usd_expenses += expense.amount
        
        # Update model fields
        self.cad_revenue = cad_revenue
        self.usd_revenue = usd_revenue
        self.cad_commission = cad_commission
        self.usd_commission = usd_commission
        self.cad_expenses = cad_expenses
        self.usd_expenses = usd_expenses
        
        # Calculate net payouts
        self.cad_payout = cad_revenue - cad_commission - cad_expenses
        self.usd_payout = usd_revenue - usd_commission - usd_expenses
        
        # Calculate final amounts (after currency conversion)
        if self.exchange_rate:
            # Convert USD to CAD and add to CAD total
            self.final_cad_amount = self.cad_payout + (self.usd_payout * self.exchange_rate)
            # Convert CAD to USD and add to USD total
            self.final_usd_amount = self.usd_payout + (self.cad_payout / self.exchange_rate)
        else:
            self.final_cad_amount = self.cad_payout
            self.final_usd_amount = self.usd_payout
        
        # Link related expenses (only if not in preview mode and payout is saved)
        if not preview_mode and self.pk:
            self.bvd_expenses.set(bvd_expenses)
            self.other_expenses.set(other_expenses)
        
        return {
            'cad_revenue': self.cad_revenue,
            'usd_revenue': self.usd_revenue,
            'cad_commission': self.cad_commission,
            'usd_commission': self.usd_commission,
            'cad_expenses': self.cad_expenses,
            'usd_expenses': self.usd_expenses,
            'cad_payout': self.cad_payout,
            'usd_payout': self.usd_payout,
            'final_cad_amount': self.final_cad_amount,
            'final_usd_amount': self.final_usd_amount,
            'total_dispatches': dispatches.count(),
            'total_bvd_expenses': bvd_expenses.count(),
            'total_other_expenses': other_expenses.count(),
        }
    
    @classmethod
    def create_for_driver_period(cls, driver, tenant, from_date, to_date, exchange_rate=1.0000):
        """Class method to create and calculate a payout for a driver and period"""
        
        # Check for existing payout
        existing = cls.objects.filter(
            driver=driver,
            tenant=tenant,
            from_date__lt=to_date,
            to_date__gt=from_date
        ).first()
        
        if existing:
            raise ValidationError(f"Payout already exists for this period: {existing}")
        
        # Create new payout
        payout = cls.objects.create(
            driver=driver,
            tenant=tenant,
            from_date=from_date,
            to_date=to_date,
            exchange_rate=exchange_rate,
            status=PayoutStatus.DRAFT
        )
        
        # Calculate totals
        calculation_result = payout.calculate_totals()
        payout.save()
        
        return payout, calculation_result

    def check_and_fix_expense_status_sync(self, user=None, force_fix=False):
        """
        Check for status synchronization issues and optionally fix them.
        
        Args:
            user: User triggering the check (for audit trail)
            force_fix: If True, automatically fix inconsistencies
            
        Returns:
            dict with sync status information and any fixes applied
        """
        result = {
            'has_issues': False,
            'issues_found': [],
            'fixes_applied': [],
            'bvd_expenses_checked': 0,
            'other_expenses_checked': 0,
            'bvd_expenses_fixed': 0,
            'other_expenses_fixed': 0
        }
        
        # Only check completed payouts
        if self.status != PayoutStatus.COMPLETED:
            result['message'] = f"Payout status is {self.status}, no sync check needed"
            return result
        
        # Check BVD expenses
        bvd_expenses = self.bvd_expenses.all()
        result['bvd_expenses_checked'] = bvd_expenses.count()
        
        for bvd in bvd_expenses:
            if bvd.status != AccountPayableStatus.PAID:
                result['has_issues'] = True
                issue = f"BVD expense {bvd.pk} status is {bvd.status}, should be PAID"
                result['issues_found'].append(issue)
                
                if force_fix:
                    try:
                        bvd.update_status(AccountPayableStatus.PAID, user=user, system_initiated=True)
                        result['fixes_applied'].append(f"Fixed BVD expense {bvd.pk}: {bvd.status} → PAID")
                        result['bvd_expenses_fixed'] += 1
                        logger.info(f"Auto-fixed BVD expense {bvd.pk} status for completed payout {self.pk}")
                    except Exception as e:
                        error_msg = f"Failed to fix BVD expense {bvd.pk}: {str(e)}"
                        result['issues_found'].append(error_msg)
                        logger.error(error_msg)
        
        # Check Other expenses
        other_expenses = self.other_expenses.all()
        result['other_expenses_checked'] = other_expenses.count()
        
        for other in other_expenses:
            issues_for_expense = []
            
            # Check main status
            if other.status != AccountPayableStatus.PAID:
                result['has_issues'] = True
                issue = f"Other expense {other.pk} status is {other.status}, should be PAID"
                issues_for_expense.append(issue)
                result['issues_found'].append(issue)
                
                if force_fix:
                    try:
                        other.update_status(AccountPayableStatus.PAID, user=user, system_initiated=True)
                        result['fixes_applied'].append(f"Fixed Other expense {other.pk}: {other.status} → PAID")
                        result['other_expenses_fixed'] += 1
                        logger.info(f"Auto-fixed Other expense {other.pk} status for completed payout {self.pk}")
                    except Exception as e:
                        error_msg = f"Failed to fix Other expense {other.pk} status: {str(e)}"
                        result['issues_found'].append(error_msg)
                        logger.error(error_msg)
            
            # Check reimbursement status for reimbursable expenses
            if (other.is_reimbursable and 
                other.reimbursement_status in [ReimbursementStatus.PENDING, ReimbursementStatus.APPROVED] and
                other.reimbursement_status != ReimbursementStatus.PAID):
                
                result['has_issues'] = True
                issue = f"Other expense {other.pk} reimbursement status is {other.reimbursement_status}, should be PAID"
                issues_for_expense.append(issue)
                result['issues_found'].append(issue)
                
                if force_fix:
                    try:
                        other.update_reimbursement_status(ReimbursementStatus.PAID, user=user, system_initiated=True)
                        result['fixes_applied'].append(f"Fixed Other expense {other.pk} reimbursement: {other.reimbursement_status} → PAID")
                        logger.info(f"Auto-fixed Other expense {other.pk} reimbursement status for completed payout {self.pk}")
                    except Exception as e:
                        error_msg = f"Failed to fix Other expense {other.pk} reimbursement status: {str(e)}"
                        result['issues_found'].append(error_msg)
                        logger.error(error_msg)
        
        # Log summary
        if result['has_issues']:
            if force_fix:
                logger.warning(
                    f"Payout {self.pk} sync check: Found {len(result['issues_found'])} issues, "
                    f"applied {len(result['fixes_applied'])} fixes"
                )
            else:
                logger.warning(
                    f"Payout {self.pk} sync check: Found {len(result['issues_found'])} sync issues "
                    f"(use force_fix=True to auto-fix)"
                )
        else:
            logger.info(f"Payout {self.pk} sync check: All expenses properly synchronized")
        
        return result

