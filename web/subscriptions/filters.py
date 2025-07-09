from django_filters import FilterSet, CharFilter, ChoiceFilter
from django import forms
from datetime import datetime
from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import UserPassesTestMixin
from subscriptions.models import TenantSubscription, UsagePeriod


class SubscriptionFilter(FilterSet):
    tenant = CharFilter(field_name="tenant__name", lookup_expr="icontains")
    plan = CharFilter(field_name="plan__name", lookup_expr="icontains")
    status = ChoiceFilter(
        choices=[("active", "Active"), ("expired", "Expired"), ("inactive", "Inactive")]
    )

    class Meta:
        model = TenantSubscription
        fields = ["tenant", "plan", "status"]


class UsageFilter(FilterSet):
    tenant = CharFilter(
        field_name="tenant__name",
        lookup_expr="icontains",
        label="Tenant name contains",  # Added label for tenant
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Search tenant..."}
        ),
    )

    period = CharFilter(
        method="filter_period",
        label="Billing Period",  # Added label for period
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "month",
                "placeholder": "Select month...",
            }
        ),
    )

    def filter_period(self, queryset, name, value):
        """Custom filter method for period"""
        if value:
            try:
                date = datetime.strptime(value, "%Y-%m")
                return queryset.filter(
                    Q(start_date__year=date.year) & Q(start_date__month=date.month)
                )
            except (ValueError, TypeError):
                return queryset
        return queryset

    class Meta:
        model = UsagePeriod
        fields = ["tenant", "period"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set initial month to current month
        current_date = timezone.now()
        self.form.fields["period"].initial = current_date.strftime("%Y-%m")


# Mixins
class SuperAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("You must be a super admin to access this page.")
        return super().handle_no_permission()


class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.profile.role == "admin"

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("You must be a super admin to access this page.")
        return super().handle_no_permission()
