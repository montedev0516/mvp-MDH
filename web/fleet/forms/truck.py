from django import forms
from fleet.models.truck import Truck, TruckStatus, OwnershipType


class TruckForm(forms.ModelForm):
    class Meta:
        model = Truck
        fields = [
            "unit",
            "plate",
            "vin",
            "make",
            "model",
            "value",
            "year",
            "country",
            "state",
            "registration",
            "ownership_type",
            "tracking",
            "leave_date",
            "still_working",
            "is_trailer",
            "trailer_number",
            "trailer_capacity",
            "company_pays_fuel_cost",
            "all_fuel_toll_cards",
            "ifta_group",
            "terminal",
            "tour",
            "weight",
            "capacity",
            "status",
            "is_active",
            "notes",
            "carrier"
        ]
        widgets = {
            "leave_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "value": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "weight": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make required fields
        self.fields["unit"].required = True
        self.fields["plate"].required = True
        self.fields["vin"].required = True
        
        # Add help text
        self.fields["vin"].help_text = "17-character Vehicle Identification Number"
        self.fields["unit"].help_text = "Unique identifier for the truck"
        
        # Set choices for status
        self.fields["status"].initial = TruckStatus.ACTIVE
        self.fields["ownership_type"].initial = OwnershipType.OWNED
        
        # Filter carrier by tenant
        if tenant:
            self.fields["carrier"].queryset = self.fields["carrier"].queryset.filter(
                tenant=tenant
            )
            self.fields["carrier"].required = False

    def clean_vin(self):
        """Validate VIN number"""
        vin = self.cleaned_data.get('vin')
        if vin:
            if len(vin) != 17:
                raise forms.ValidationError("VIN must be exactly 17 characters long")
        return vin
