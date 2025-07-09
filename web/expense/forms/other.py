import logging
from django import forms
from django.utils import timezone
from expense.models import OtherExpense, AccountPayableStatus
from models.models import Currency
from expense.models import ReimbursementStatus

logger = logging.getLogger("django")


class BasicOtherExpenseForm(forms.ModelForm):
    """Simplified form for quick Other Expense entry with only essential fields"""
    
    class Meta:
        model = OtherExpense
        fields = ["date", "name", "category", "amount", "currency", "driver", "truck"]
        widgets = {
            "date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                    "required": "required"
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "currency": forms.Select(attrs={"class": "form-control"}, choices=Currency.choices),
            "driver": forms.Select(attrs={"class": "form-control"}),
            "truck": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # All fields are required for basic form
        for field in self.fields:
            self.fields[field].required = True
            
        # Set defaults
        self.fields["currency"].initial = Currency.CAD
        self.fields["category"].initial = "OTHER"
        
        # Filter by tenant
        if tenant:
            self.fields["driver"].queryset = self.fields["driver"].queryset.filter(
                tenant=tenant, is_active=True
            )
            self.fields["truck"].queryset = self.fields["truck"].queryset.filter(
                tenant=tenant, is_active=True
            )


class OtherExpenseForm(forms.ModelForm):
    """Complete form for Other Expense records with all fields"""
    
    class Meta:
        model = OtherExpense
        exclude = ["tenant", "is_active", "deleted_at"]
        widgets = {
            "date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                    "required": "required"
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "currency": forms.Select(attrs={"class": "form-control"}, choices=Currency.choices),
            "tax_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tax_type": forms.Select(attrs={"class": "form-control"}),
            "receipt_image": forms.FileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "receipt_number": forms.TextInput(attrs={"class": "form-control"}),
            "vendor_name": forms.TextInput(attrs={"class": "form-control"}),
            "vendor_location": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_reimbursable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "reimbursement_status": forms.Select(attrs={"class": "form-control"}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "payment_reference": forms.TextInput(attrs={"class": "form-control"}),
            "odometer": forms.NumberInput(attrs={"class": "form-control"}),
            "driver": forms.Select(attrs={"class": "form-control"}),
            "truck": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}, choices=AccountPayableStatus.choices),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        logger.info("Initializing OtherExpenseForm")
        super().__init__(*args, **kwargs)
        
        # Make required fields - keep minimal
        required_fields = [
            "date", "name", "category", "amount", "currency"
        ]
        for field in required_fields:
            self.fields[field].required = True
            
        # Set default values
        self.fields["currency"].initial = Currency.CAD
        self.fields["status"].initial = AccountPayableStatus.PENDING
        self.fields["tax_type"].initial = "NONE"
        self.fields["category"].initial = "OTHER"
        self.fields["payment_method"].initial = "CASH"
        self.fields["reimbursement_status"].initial = ReimbursementStatus.PENDING
        self.fields["is_reimbursable"].initial = True
        
        # Set input formats for date field
        self.fields["date"].input_formats = [
            "%Y-%m-%dT%H:%M",  # HTML5 datetime-local
            "%Y-%m-%d %H:%M:%S",  # Standard datetime
            "%Y-%m-%d %H:%M",  # Standard datetime without seconds
            "%Y-%m-%d",  # Just date
        ]
        
        # Set initial date if not provided
        if not self.instance.pk and not self.initial.get('date'):
            self.initial['date'] = timezone.now()
        
        # Filter querysets by tenant if provided
        if tenant:
            if "driver" in self.fields:
                self.fields["driver"].queryset = self.fields["driver"].queryset.filter(
                    tenant=tenant,
                    is_active=True
                )
            if "truck" in self.fields:
                self.fields["truck"].queryset = self.fields["truck"].queryset.filter(
                    tenant=tenant,
                    is_active=True
                )
            
            # Store tenant for validation
            self._tenant = tenant
            
            # Set tenant on instance to prevent validation errors
            if hasattr(self, "instance"):
                self.instance.tenant = tenant

    def clean(self):
        """Basic validation - rely on model for business logic"""
        logger.info("Starting OtherExpenseForm cleaning")
        cleaned_data = super().clean()
        
        # Only essential validations here - let model handle rest
        date = cleaned_data.get("date")
        if not date:
            self.add_error("date", "Date is required")
            
        return cleaned_data 