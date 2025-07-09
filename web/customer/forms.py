from django import forms
from fleet.models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        exclude = ["created_at", "updated_at", "tenant", "deleted_at"]
