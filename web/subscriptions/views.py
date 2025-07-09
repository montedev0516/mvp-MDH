# Create your views here.
import logging
from datetime import timezone as dt_tz
from django.views.generic import (
    CreateView,
    UpdateView,
    ListView,
    DetailView,
    DeleteView,
)
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django_filters.views import FilterView
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse_lazy
from django_tables2 import SingleTableView
from django.utils import timezone
from django.db.models import Sum, Count
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.http import Http404
from django_tables2 import SingleTableMixin
from datetime import datetime
from tenant.models import Tenant
from subscriptions.models import (
    SubscriptionPlan,
    TenantSubscription,
    UsagePeriod,
    UsageLog,
    QuotaAlert,
    QuotaService,
)

from subscriptions.tables import (
    TenantSubscriptionTable,
    UsageTable,
    SubscriptionPlanTable,
    UsageLogTable,
)
from subscriptions.filters import (
    SubscriptionFilter,
    UsageFilter,
    SuperAdminRequiredMixin,
    AdminRequiredMixin,
)
from subscriptions.forms import SubscriptionForm

logger = logging.getLogger("django")


class SubscriptionPlanListView(
    LoginRequiredMixin, SuperAdminRequiredMixin, SingleTableView
):
    model = SubscriptionPlan
    table_class = SubscriptionPlanTable
    template_name = "subscriptions/plan_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_subscriptions"] = TenantSubscription.objects.filter(
            is_active=True
        ).count()
        return context


class SubscriptionPlanCreateView(
    LoginRequiredMixin, SuperAdminRequiredMixin, CreateView
):
    model = SubscriptionPlan
    template_name = "subscriptions/plan_form.html"
    success_url = reverse_lazy("subscriptions:plan_list")
    fields = [
        "name",
        "description",
        "max_active_drivers",
        "max_active_trucks",
        "max_organizations",
        "monthly_order_limit",
        "monthly_license_limit",
        "monthly_token_limit",
        "storage_limit_mb",
        "price_monthly",
        "price_yearly",
        "is_custom",
    ]


class TenantSubscriptionListView(
    LoginRequiredMixin, SuperAdminRequiredMixin, SingleTableView
):
    model = TenantSubscription
    table_class = TenantSubscriptionTable
    template_name = "subscriptions/subscription_list.html"
    filterset_class = SubscriptionFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_count"] = TenantSubscription.objects.filter(
            is_active=True
        ).count()
        context["expiring_soon"] = TenantSubscription.objects.filter(
            is_active=True, end_date__lte=timezone.now() + timezone.timedelta(days=30)
        ).count()
        return context


class UsageMonitoringView(
    LoginRequiredMixin, SuperAdminRequiredMixin, SingleTableMixin, FilterView
):
    model = UsagePeriod
    table_class = UsageTable
    template_name = "subscriptions/usage_monitoring.html"
    filterset_class = UsageFilter

    def get_queryset(self):
        qs = (
            UsagePeriod.objects.select_related("tenant")
            .filter(is_active=True)
            .exclude(
                tokens_used=0,
                orders_processed=0,
                licenses_processed=0,
                storage_used_mb=0,
            )
        )

        # Get the filter
        filter_set = self.filterset_class(self.request.GET, queryset=qs)
        return filter_set.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = self.request.user.profile.tenant

        # Add debug logging
        logger.debug(f"Current user tenant: {tenant.id} ({tenant.name})")

        # Get active alerts with more detailed logging
        active_alerts = QuotaAlert.objects.filter(
            tenant=tenant,
            acknowledged=False,
        ).order_by("-notified_at")

        # Debug logging for each alert
        for alert in active_alerts:
            logger.debug(
                f"Found alert - ID: {alert.id}, Tenant: {alert.tenant.id}, Feature: {alert.feature}"
            )

        # Apply filters to get filtered queryset
        filtered_qs = self.get_queryset()

        # Get aggregate stats for filtered queryset
        total_usage = filtered_qs.aggregate(
            total_orders=Sum("orders_processed"),
            total_licenses=Sum("licenses_processed"),
            total_tokens=Sum("tokens_used"),
            total_storage=Sum("storage_used_mb"),
        )

        # Get alert counts
        alert_counts = (
            QuotaAlert.objects.filter(acknowledged=False)
            .values("alert_type")
            .annotate(count=Count("id"))
        )

        context.update(
            {
                "active_alerts": active_alerts,
                "total_usage": total_usage,
                "alert_counts": alert_counts,
            }
        )

        return context


class SubscriptionPlanUpdateView(
    LoginRequiredMixin, SuperAdminRequiredMixin, UpdateView
):
    model = SubscriptionPlan
    template_name = "subscriptions/plan_form.html"
    success_url = reverse_lazy("subscriptions:plan_list")
    fields = [
        "name",
        "description",
        "max_active_drivers",
        "max_active_trucks",
        "max_organizations",
        "monthly_order_limit",
        "monthly_license_limit",
        "monthly_token_limit",
        "storage_limit_mb",
        "price_monthly",
        "price_yearly",
        "is_custom",
    ]


class SubscriptionPlanDeleteView(
    LoginRequiredMixin, SuperAdminRequiredMixin, DeleteView
):
    model = SubscriptionPlan
    success_url = reverse_lazy("subscriptions:plan_list")

    def get_queryset(self):
        # Only allow deletion of non-custom plans
        return super().get_queryset().filter(is_custom=False)


class SubscriptionUpdateView(LoginRequiredMixin, SuperAdminRequiredMixin, UpdateView):
    model = TenantSubscription
    form_class = SubscriptionForm
    template_name = "subscriptions/subscription_form.html"
    success_url = reverse_lazy("subscriptions:tenant_subscription_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Subscription - {self.object.tenant.name}"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Subscription for {self.object.tenant.name} has been updated successfully.",
        )
        return response


class TenantUsageDetailView(
    LoginRequiredMixin, AdminRequiredMixin, SingleTableMixin, DetailView
):
    model = UsagePeriod
    template_name = "subscriptions/tenant_usage_detail.html"
    context_object_name = "usage"
    table_class = UsageLogTable
    table_pagination = {"per_page": 10}

    def get_table_data(self):
        """Get the usage logs for this tenant"""
        return (
            UsageLog.objects.filter(tenant=self.get_object().tenant)
            .select_related("content_type", "usage_period")
            .order_by("-timestamp")
        )

    def get_object(self, queryset=None):
        """Get or create usage period for the tenant"""
        tenant_id = self.kwargs.get("pk")
        tenant = get_object_or_404(Tenant, id=tenant_id)

        # Get current billing period dates
        now = timezone.now()
        subscription = tenant.get_active_subscription()

        if not subscription:
            raise Http404("No active subscription found for tenant")

        # Calculate period dates based on billing cycle
        if subscription.billing_cycle == "monthly":
            start_date = datetime(now.year, now.month, 1, tzinfo=dt_tz.utc)
            if now.month == 12:
                end_date = datetime(now.year + 1, 1, 1, tzinfo=dt_tz.utc)
            else:
                end_date = datetime(now.year, now.month + 1, 1, tzinfo=dt_tz.utc)
        else:  # yearly
            start_date = datetime(now.year, 1, 1, tzinfo=dt_tz.utc)
            end_date = datetime(now.year + 1, 1, 1, tzinfo=dt_tz.utc)

        # First try to get an existing non-empty period
        usage_period = (
            UsagePeriod.objects.filter(
                tenant=tenant, start_date__lte=now, end_date__gt=now
            )
            .exclude(
                tokens_used=0,
                orders_processed=0,
                licenses_processed=0,
                storage_used_mb=0,
            )
            .first()
        )

        if not usage_period:
            # If no non-empty period exists, get or create one
            usage_period, created = UsagePeriod.objects.get_or_create(
                tenant=tenant,
                start_date=start_date,
                end_date=end_date,
                defaults={
                    "orders_processed": 0,
                    "licenses_processed": 0,
                    "tokens_used": 0,
                    "storage_used_mb": 0,
                },
            )

        return usage_period

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = self.get_object().tenant
        quota_service = QuotaService(tenant)

        # Get total usage for the tenant (across all periods)
        total_usage = UsagePeriod.objects.filter(tenant=tenant).aggregate(
            total_orders=Sum("orders_processed"),
            total_licenses=Sum("licenses_processed"),
            total_tokens=Sum("tokens_used"),
            total_storage=Sum("storage_used_mb"),
        )

        # Calculate usage percentages
        context["usage_stats"] = {
            "orders": {
                "current": self.get_object().orders_processed,
                "total": total_usage["total_orders"] or 0,
                "limit": quota_service.get_limit("monthly_order_limit"),
                "percentage": (
                    self.get_object().orders_processed
                    / quota_service.get_limit("monthly_order_limit")
                    * 100
                )
                if quota_service.get_limit("monthly_order_limit") > 0
                else 0,
            },
            "licenses": {
                "current": self.object.licenses_processed,
                "total": total_usage["total_licenses"] or 0,
                "limit": quota_service.get_limit("monthly_license_limit"),
                "percentage": (
                    self.object.licenses_processed
                    / quota_service.get_limit("monthly_license_limit")
                    * 100
                )
                if quota_service.get_limit("monthly_license_limit") > 0
                else 0,
            },
            "tokens": {
                "current": self.object.tokens_used,
                "total": total_usage["total_tokens"] or 0,
                "limit": quota_service.get_limit("monthly_token_limit"),
                "percentage": (
                    self.object.tokens_used
                    / quota_service.get_limit("monthly_token_limit")
                    * 100
                )
                if quota_service.get_limit("monthly_token_limit") > 0
                else 0,
            },
            "storage": {
                "current": self.object.storage_used_mb,
                "total": total_usage["total_storage"] or 0,
                "limit": quota_service.get_limit("storage_limit_mb"),
                "percentage": (
                    self.object.storage_used_mb
                    / quota_service.get_limit("storage_limit_mb")
                    * 100
                )
                if quota_service.get_limit("storage_limit_mb") > 0
                else 0,
            },
        }

        # Get recent usage logs with related objects
        context["recent_logs"] = (
            UsageLog.objects.filter(tenant=tenant)
            .select_related("content_type", "usage_period")
            .order_by("-timestamp")[:50]
        )

        # Get active alerts
        context["active_alerts"] = QuotaAlert.objects.filter(
            tenant=tenant, acknowledged=False
        ).order_by("-notified_at")

        return context


class AlertListView(LoginRequiredMixin, ListView):
    model = QuotaAlert
    template_name = "subscriptions/alert_list.html"
    context_object_name = "alerts"

    def get_queryset(self):
        return QuotaAlert.objects.filter(
            tenant=self.request.user.profile.tenant, acknowledged=False
        ).select_related("tenant")


@login_required
@require_http_methods(["POST"])
def acknowledge_alert(request, pk):
    try:
        user_tenant = request.user.profile.tenant
        logger.debug(
            f"Processing alert acknowledgment - Alert: {pk}, User Tenant: {user_tenant.id}"
        )

        alert = QuotaAlert.objects.filter(pk=pk).select_related("tenant").first()

        if not alert:
            logger.warning(f"Alert {pk} does not exist")
            return JsonResponse(
                {"status": "error", "message": "Alert not found"}, status=404
            )

        if alert.tenant != user_tenant:
            logger.warning(
                f"Tenant mismatch - Alert Tenant: {alert.tenant.id}, User Tenant: {user_tenant.id}"
            )
            return JsonResponse(
                {
                    "status": "error",
                    "message": "You don't have permission to acknowledge this alert",
                },
                status=403,
            )

        alert.acknowledged = True
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save()

        logger.info(f"Successfully acknowledged alert {pk} for tenant {user_tenant.id}")
        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Error acknowledging alert {pk}: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@login_required
def debug_alerts(request, pk):
    alert = QuotaAlert.objects.filter(pk=pk, tenant=request.user.profile.tenant).first()

    if alert:
        return JsonResponse(
            {"exists": True, "id": str(alert.pk), "tenant": str(alert.tenant.pk)}
        )
    return JsonResponse(
        {
            "exists": False,
            "queried_id": str(pk),
            "tenant": str(request.user.profile.tenant.pk),
        }
    )
