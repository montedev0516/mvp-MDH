from django.db import models
from models.models import BaseModel
from fleet.models import Carrier
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation

class EmploymentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ON_LEAVE = "on_leave", "On Leave"
    TERMINATED = "terminated", "Terminated"

class DutyStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    ON_DUTY = "on_duty", "On Duty"
    ON_LEAVE = "on_leave", "On Leave"
    UNASSIGNED = "unassigned", "Unassigned"

class DriverLicense(BaseModel):
    # Required fields (from the license itself)
    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=255)
    date_of_birth = models.DateTimeField(null=True, blank=True)
    expiry_date = models.DateTimeField(null=True, blank=True)
    
    # Optional fields (may not be present or readable)
    issued_date = models.DateTimeField(null=True, blank=True)
    gender = models.CharField(max_length=255, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    province = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    
    # Japanese-specific fields
    license_type = models.CharField(max_length=255, null=True, blank=True, help_text="Type of license (e.g., 普通車)")
    conditions = models.CharField(max_length=255, null=True, blank=True, help_text="License conditions or restrictions (e.g., AT車に限る)")
    license_class = models.CharField(max_length=255, null=True, blank=True, help_text="License class or grade (e.g., 優良)")
    public_safety_commission = models.CharField(max_length=255, null=True, blank=True, help_text="Issuing public safety commission (e.g., 公安委員会)")
    
    # Metadata fields (for processing)
    completion_tokens = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    llm_model_name = models.CharField(max_length=255)
    uploaded_file_name = models.CharField(max_length=255)
    file_save_path = models.CharField(max_length=255)
    
    # Organizational fields (optional)
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.name} {self.license_number}"

class Driver(BaseModel):
    # Personal Information
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField(null=True, blank=True)
    license_number = models.CharField(max_length=50, unique=True)

    # Contact Information
    phone = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    emergency_contact = models.JSONField(null=True, blank=True)

    # Address Information
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=50, null=True, blank=True)
    zip_code = models.CharField(max_length=10, null=True, blank=True)
    country = models.CharField(max_length=50, null=True, blank=True)

    # Employment Information
    employee_id = models.CharField(max_length=50, unique=True)
    hire_date = models.DateField()
    joining_date = models.DateTimeField(default=timezone.now)  # Required field from initial migration
    termination_date = models.DateField(null=True, blank=True)
    still_working = models.BooleanField(default=True)  # Required field from initial migration
    
    is_active = models.BooleanField(default=True)
    # notes = models.TextField(blank=True)

    # Relationships
    drivers_license = models.ForeignKey(DriverLicense, on_delete=models.SET_NULL, null=True, blank=True)
    carrier = models.ForeignKey(Carrier, on_delete=models.SET_NULL, null=True, blank=True)
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)

    class Meta:
        ordering = ["first_name", "last_name"]
        verbose_name = "Driver"
        verbose_name_plural = "Drivers"

    def __str__(self):
        try:
            employment_status = self.driveremployment.employment_status
        except DriverEmployment.DoesNotExist:
            employment_status = 'No Employment Record'
        return f"{self.first_name} {self.last_name} ({employment_status})"

    def get_full_name(self):
        """Return the driver's full name."""
        return f"{self.first_name} {self.last_name}"

    def is_license_valid(self):
        """Check if driver's license is valid and not expired"""
        if not self.drivers_license:
            return False
        
        if self.drivers_license.expiry_date:
            return self.drivers_license.expiry_date > timezone.now()
        
        return True

    def is_qualified_for_truck(self, truck):
        """
        Enhanced qualification check for truck assignment.
        Checks carrier matching, license validity, and employment status.
        """
        # Both driver and truck must have a carrier assigned
        if not self.carrier or not truck.carrier:
            return False, "Driver or truck not assigned to carrier"

        # Driver and truck must belong to the same carrier
        if self.carrier != truck.carrier:
            return False, "Driver and truck belong to different carriers"
        
        # Check license validity
        if not self.is_license_valid():
            return False, "Driver license is invalid or expired"
        
        # Check employment status
        try:
            employment = self.driveremployment
            if employment.employment_status != EmploymentStatus.ACTIVE:
                return False, f"Driver employment status is {employment.get_employment_status_display()}"
            
            if employment.duty_status not in [DutyStatus.AVAILABLE, DutyStatus.ON_DUTY]:
                return False, f"Driver duty status is {employment.get_duty_status_display()}"
        except DriverEmployment.DoesNotExist:
            return False, "Driver has no employment record"
        
        # All checks passed
        return True, "Qualified"

    def get_current_status(self):
        """Get current comprehensive status of driver"""
        try:
            employment = self.driveremployment
            return {
                'employment_status': employment.employment_status,
                'duty_status': employment.duty_status,
                'is_available': employment.employment_status == EmploymentStatus.ACTIVE and employment.duty_status == DutyStatus.AVAILABLE,
                'can_be_assigned': employment.employment_status == EmploymentStatus.ACTIVE and employment.duty_status in [DutyStatus.AVAILABLE, DutyStatus.ON_DUTY]
            }
        except DriverEmployment.DoesNotExist:
            return {
                'employment_status': None,
                'duty_status': None,
                'is_available': False,
                'can_be_assigned': False
            }

    def save(self, *args, **kwargs):
        """Override save to ensure DriverEmployment is created"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Create DriverEmployment record for new drivers
        if is_new:
            DriverEmployment.objects.get_or_create(
                driver=self,
                defaults={
                    'tenant': self.tenant,
                    'employment_status': EmploymentStatus.ACTIVE,
                    'duty_status': DutyStatus.AVAILABLE,
                }
            )

class DriverEmployment(BaseModel):
    driver = models.OneToOneField(Driver, on_delete=models.CASCADE)
    status_history = GenericRelation('dispatch.StatusHistory')
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE, null=True)

    # Status Fields (with history)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE
    )
    duty_status = models.CharField(
        max_length=20,
        choices=DutyStatus.choices,
        default=DutyStatus.AVAILABLE
    )

    # Location Tracking
    current_location = models.CharField(max_length=255, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    location_history = models.JSONField(null=True, blank=True)

    # Current Assignment
    current_assignment = models.ForeignKey(
        "dispatch.DriverTruckAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_driver_assignment"
    )

    # Preferences and Settings
    max_hours_per_week = models.IntegerField(default=40)
    preferred_routes = models.JSONField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.driver.first_name} {self.driver.last_name} - {self.employment_status}"
    
    def get_current_status(self, check_date=None):
        if check_date is None:
            check_date = timezone.now()
            
        if self.employment_status == EmploymentStatus.ACTIVE:
            if self.duty_status == DutyStatus.AVAILABLE:
                return "Available"
            elif self.duty_status == DutyStatus.ON_DUTY:
                return "On Duty"
            elif self.duty_status == DutyStatus.ON_LEAVE:
                return "On Leave"
            else:
                return "Unassigned"
            
        return "Inactive"
    
    def is_available(self, start_date, end_date):
        if self.employment_status != EmploymentStatus.ACTIVE:
            return False
        
        if self.duty_status != DutyStatus.AVAILABLE:
            return False
        
        return True

    def log_status_change(self, old_status, new_status, user=None):
        """Log status change to status history"""
        from dispatch.models import StatusHistory
        StatusHistory.log_status_change(
            obj=self,
            old_status=old_status,
            new_status=new_status,
            user=user,
            metadata={
                'driver_name': f"{self.driver.first_name} {self.driver.last_name}",
                'driver_id': str(self.driver.id),
                'employment_status': self.employment_status,
            }
        )

    def save(self, *args, **kwargs):
        """Override save to ensure tenant is set from driver"""
        if not self.tenant_id and self.driver_id:
            # Use driver_id to avoid potential None issues
            try:
                driver = Driver.objects.get(id=self.driver_id)
                self.tenant = driver.tenant
            except Driver.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
            