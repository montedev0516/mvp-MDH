from django import forms
from fleet.models.carrier import Carrier


class CarrierForm(forms.ModelForm):
    class Meta:
        model = Carrier
        fields = [
            "name",
            "legal_name",
            "business_number",
            "mc_number",
            "dot_number",
            "email",
            "phone",
            "website",
            "address",
            "city",
            "state",
            "zip_code",
            "country",
            "total_trucks",
            "total_drivers",
            "status",
            "is_active",
            "notes"
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add any field customizations here
        self.fields['total_trucks'].widget.attrs.update({'min': '0'})
        self.fields['total_drivers'].widget.attrs.update({'min': '0'})
        self.fields['phone'].widget.attrs.update({'placeholder': '+1234567890'})
        self.fields['zip_code'].widget.attrs.update({'placeholder': '12345'})
