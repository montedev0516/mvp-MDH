import logging
from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from expense.models import Payout, PayoutStatus
from models.models import Currency

logger = logging.getLogger("django")


class PayoutCalculationForm(forms.ModelForm):
    """Form for calculating and creating driver payouts"""
    
    class Meta:
        model = Payout
        fields = [
            "driver", "from_date", "to_date", "exchange_rate",
            "cad_revenue", "cad_commission", "cad_expenses", 
            "usd_revenue", "usd_commission", "usd_expenses"
        ]
        widgets = {
            "driver": forms.Select(attrs={"class": "form-control"}),
            "from_date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control",
                    "required": "required"
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "to_date": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local", 
                    "class": "form-control",
                    "required": "required"
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "exchange_rate": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.0001",
                "placeholder": "1.0000"
            }),
            "cad_revenue": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01",
                "readonly": "readonly"
            }),
            "cad_commission": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01",
                "readonly": "readonly"
            }),
            "cad_expenses": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01", 
                "readonly": "readonly"
            }),
            "usd_revenue": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01",
                "readonly": "readonly"
            }),
            "usd_commission": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01",
                "readonly": "readonly"
            }),
            "usd_expenses": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01",
                "readonly": "readonly"
            }),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Required fields
        required_fields = ["driver", "from_date", "to_date"]
        for field in required_fields:
            self.fields[field].required = True
            
        # Set defaults
        self.fields["exchange_rate"].initial = 1.0000
        
        # Set default date range (previous month)
        if not self.instance.pk:
            today = timezone.now().date()
            first_of_month = today.replace(day=1)
            last_month = first_of_month - timedelta(days=1)
            from_date = last_month.replace(day=1)
            to_date = first_of_month - timedelta(seconds=1)
            
            self.fields["from_date"].initial = from_date
            self.fields["to_date"].initial = to_date
        
        # Filter drivers by tenant
        if tenant:
            self.fields["driver"].queryset = self.fields["driver"].queryset.filter(
                tenant=tenant, is_active=True
            )
            self._tenant = tenant

    def clean(self):
        cleaned_data = super().clean()
        
        from_date = cleaned_data.get("from_date")
        to_date = cleaned_data.get("to_date")
        
        if from_date and to_date:
            if from_date >= to_date:
                raise ValidationError("From date must be before to date")
                
            # Check for overlapping payouts
            driver = cleaned_data.get("driver")
            if driver and self._tenant:
                overlapping = Payout.objects.filter(
                    tenant=self._tenant,
                    driver=driver,
                    from_date__lt=to_date,
                    to_date__gt=from_date
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if overlapping.exists():
                    raise ValidationError(
                        f"A payout already exists for this driver in the selected period. "
                        f"Overlapping payout: {overlapping.first()}"
                    )
        
        return cleaned_data


class PayoutUpdateForm(forms.ModelForm):
    """Form for updating payout details"""
    
    class Meta:
        model = Payout
        fields = [
            "status", "exchange_rate", "final_cad_amount", "final_usd_amount"
        ]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "exchange_rate": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.0001"
            }),
            "final_cad_amount": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01"
            }),
            "final_usd_amount": forms.NumberInput(attrs={
                "class": "form-control", 
                "step": "0.01"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements based on status
        if self.instance and self.instance.status in [PayoutStatus.PROCESSING, PayoutStatus.COMPLETED]:
            self.fields["final_cad_amount"].required = True
            self.fields["final_usd_amount"].required = True


class PayoutFilterForm(forms.Form):
    """Form for filtering payouts in list view"""
    
    driver = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Drivers",
        widget=forms.Select(attrs={"class": "form-control"})
    )
    status = forms.ChoiceField(
        choices=[("", "All Statuses")] + list(PayoutStatus.choices),
        required=False,
        widget=forms.Select(attrs={"class": "form-control"})
    )
    from_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    to_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
    )
    
    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if tenant:
            from fleet.models import Driver
            self.fields["driver"].queryset = Driver.objects.filter(
                tenant=tenant, is_active=True
            )


class PayoutBulkActionForm(forms.Form):
    """Form for bulk actions on payouts"""
    
    ACTION_CHOICES = [
        ("", "Select Action"),
        ("mark_processing", "Mark as Processing"),
        ("mark_completed", "Mark as Completed"),
        ("recalculate", "Recalculate Amounts"),
        ("export", "Export to Excel"),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        widget=forms.Select(attrs={"class": "form-control"})
    )
    payout_ids = forms.CharField(
        widget=forms.HiddenInput(),
        required=True
    )
    
    def clean_payout_ids(self):
        ids = self.cleaned_data.get("payout_ids", "")
        try:
            return [id.strip() for id in ids.split(",") if id.strip()]
        except:
            raise ValidationError("Invalid payout IDs") 