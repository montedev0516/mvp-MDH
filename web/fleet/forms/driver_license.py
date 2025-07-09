from django import forms  # type: ignore
from fleet.models.driver import DriverLicense


class DriverLicenseForm(forms.ModelForm):
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
            "public_safety_commission",
            "llm_model_name",
            "uploaded_file_name",
            "file_save_path"
        ]
        widgets = {
            "date_of_birth": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "issued_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "expiry_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make required fields
        self.fields["name"].required = True
        self.fields["license_number"].required = True
        self.fields["expiry_date"].required = True
        
        # Add help text
        self.fields["license_type"].help_text = "Type of license (e.g., 普通車)"
        self.fields["conditions"].help_text = "License conditions or restrictions"
        self.fields["license_class"].help_text = "License class or grade"
        self.fields["public_safety_commission"].help_text = "Issuing public safety commission"
