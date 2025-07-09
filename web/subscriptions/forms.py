from django.forms import ModelForm, DateTimeInput
from .models import (
    SubscriptionPlan,
    TenantSubscription,
)


class SubscriptionForm(ModelForm):
    class Meta:
        model = TenantSubscription
        fields = [
            "plan",
            "start_date",
            "end_date",
            "is_active",
            "auto_renew",
            "billing_cycle",
        ]
        widgets = {
            "start_date": DateTimeInput(attrs={"type": "datetime-local"}),
            "end_date": DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes
        for field in self.fields.values():
            if isinstance(field.widget, DateTimeInput):
                field.widget.attrs["class"] = "form-control"
            else:
                field.widget.attrs["class"] = (
                    "form-select"
                    if field.widget.input_type == "select"
                    else "form-control"
                )

        # Set up plan choices
        self.fields["plan"].queryset = SubscriptionPlan.objects.all()
