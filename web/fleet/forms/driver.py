import json
from django import forms  # type: ignore
from django.forms import ModelForm  # type: ignore
from fleet.models.driver import Driver, DriverLicense


class DriverLicenseForm(ModelForm):
    class Meta:
        model = DriverLicense
        fields = [
            "name",
            "license_number",
            "date_of_birth",
            "expiry_date",
            "issued_date",
            "gender",
            "address",
            "country",
            "province",
            "state",
            "license_type",
            "conditions",
            "license_class",
            "public_safety_commission"
        ]
        widgets = {
            "date_of_birth": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "issued_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "expiry_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class DriverForm(ModelForm):
    emergency_contact = forms.JSONField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make essential fields required
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["license_number"].required = True
        self.fields["phone"].required = True
        self.fields["email"].required = True
        
        # Add help text
        self.fields["emergency_contact"].help_text = "Enter JSON format: {'name': 'John Doe', 'phone': '+1234567890', 'relationship': 'Spouse'}"
        self.fields["address"].help_text = "Enter complete address"
        
        # Add placeholders
        self.fields["email"].widget.attrs["placeholder"] = "email@example.com"
        self.fields["phone"].widget.attrs["placeholder"] = "+1234567890"

    class Meta:
        model = Driver
        fields = [
            "first_name",
            "last_name",
            "date_of_birth",
            "license_number",
            "phone",
            "email",
            "emergency_contact",
            "address",
            "city",
            "state",
            "zip_code",
            "country",
            "employee_id",
            "hire_date",
            "termination_date",
            "drivers_license",
            "carrier",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "hire_date": forms.DateInput(attrs={"type": "date"}),
            "termination_date": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_emergency_contact(self):
        """Validate emergency_contact JSON data"""
        data = self.cleaned_data.get("emergency_contact")
        if data:
            try:
                if isinstance(data, str):
                    import json
                    data = json.loads(data)
                required_fields = ['name', 'phone']
                for field in required_fields:
                    if field not in data:
                        raise forms.ValidationError(f"Emergency contact must include {field}")
                return data
            except Exception as e:
                raise forms.ValidationError(f"Invalid emergency contact format: {str(e)}")
        return None
