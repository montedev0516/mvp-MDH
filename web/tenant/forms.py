from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import UserCreationForm
from tenant.models import Tenant, Role
from fleet.models import Carrier, Organization


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]


class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


class OrganizationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            "name",
            "address",
            "commission_percentage",
            "commission_currency",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "commission_percentage": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100"
            }),
            "commission_currency": forms.Select(attrs={"class": "form-select"}),
        }


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
            "is_active",
            "notes"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "legal_name": forms.TextInput(attrs={"class": "form-control"}),
            "business_number": forms.TextInput(attrs={"class": "form-control"}),
            "mc_number": forms.TextInput(attrs={"class": "form-control"}),
            "dot_number": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "website": forms.URLInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class CarrierUpdateForm(forms.ModelForm):
    class Meta:
        model = Carrier
        fields = [
            "name",
            "legal_name",
            "email",
            "phone",
            "website",
            "address",
            "city",
            "state",
            "zip_code",
            "country",
            "tax_rate",
            "tax_currency",
            "is_active",
            "notes"
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "legal_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "website": forms.URLInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "tax_rate": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100"
            }),
            "tax_currency": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[
            (Role.REGULAR_USER, "Regular User"),
            (Role.ADMIN, "Admin"),
        ],  # Removed super_admin from choices
        required=True,
        help_text="Select the role for this user",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ("email", "first_name", "last_name")
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
        }


class UserEditForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=[
            (Role.REGULAR_USER, "Regular User"),
            (Role.ADMIN, "Admin"),
        ],  # Removed super_admin from choices,
        required=True,
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(),
        required=False,
        help_text="Leave blank to keep current password",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(), required=False, help_text="Confirm new password"
    )

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "is_active"]

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and not confirm_password:
            raise ValidationError("Please confirm the new password")

        if confirm_password and not new_password:
            raise ValidationError("Please enter the new password")

        if new_password and confirm_password:
            if new_password != confirm_password:
                raise ValidationError("Passwords do not match")

        return cleaned_data


class UserAddForm(UserCreationForm):
    tenant = forms.ModelChoiceField(
        queryset=Tenant.objects.all(),
        required=True,
        help_text="Select the tenant for this user",
    )
    role = forms.ChoiceField(
        choices=[
            (Role.REGULAR_USER, "Regular User"),
            (Role.ADMIN, "Admin"),
        ],  # Removed super_admin from choices
        required=True,
        help_text="Select the role for this user",
    )

    class Meta:
        model = User
        fields = [
            "tenant",
            "username",
            "email",
            "first_name",
            "last_name",
            "password1",
            "password2",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
