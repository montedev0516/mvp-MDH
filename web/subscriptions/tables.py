from django_tables2 import Table, Column, TemplateColumn
from django.utils import timezone
from django.utils.html import mark_safe
from subscriptions.models import (
    SubscriptionPlan,
    TenantSubscription,
    UsagePeriod,
    QuotaService,
    QuotaAlert,
    UsageLog,
)


class SubscriptionPlanTable(Table):
    actions = TemplateColumn(
        template_name="subscriptions/table_actions_plan.html",
        extra_context={"edit_url": "admin:subscriptions_plan_change"},
        verbose_name="",
    )
    active_subscriptions = Column(empty_values=())

    class Meta:
        model = SubscriptionPlan
        template_name = "django_tables2/bootstrap5.html"
        fields = (
            "name",
            "price_monthly",
            "price_yearly",
            "is_custom",
            "active_subscriptions",
        )
        attrs = {"class": "table table-striped table-hover"}

    def render_active_subscriptions(self, record):
        return TenantSubscription.objects.filter(plan=record, is_active=True).count()


class TenantSubscriptionTable(Table):
    tenant = Column(accessor="tenant.name")
    plan = Column(accessor="plan.name")
    status = Column(empty_values=())
    actions = TemplateColumn(
        template_name="subscriptions/table_actions_subscription.html", verbose_name=""
    )

    class Meta:
        model = TenantSubscription
        template_name = "django_tables2/bootstrap5.html"
        fields = ("tenant", "plan", "start_date", "end_date", "billing_cycle", "status")
        attrs = {"class": "table table-striped table-hover"}

    def render_status(self, record):
        if not record.is_active:
            return "Inactive"
        if record.end_date < timezone.now():
            return "Expired"
        return "Active"


class UsageTable(Table):
    tenant = Column(accessor="tenant.name")
    storage_delta_mb = Column(
        verbose_name="Storage Delta",
        accessor="storage_used_mb",  # Add explicit accessor
    )
    usage_percentage = Column(empty_values=())
    alerts = Column(empty_values=())

    class Meta:
        model = UsagePeriod
        template_name = "django_tables2/bootstrap5.html"
        fields = (
            "tenant",
            "orders_processed",
            "licenses_processed",
            "tokens_used",
            "storage_delta_mb",
            "usage_percentage",
            "alerts",
        )
        attrs = {"class": "table table-striped table-hover"}

    def render_storage_delta_mb(self, value):
        """Format storage value with MB unit"""
        if value is None or value == 0:
            return "-"
        # Add formatting for nonzero values
        return mark_safe(f"{value:.2f} MB")

    def render_usage_percentage(self, record):
        quota_service = QuotaService(record.tenant)
        token_limit = quota_service.get_limit("monthly_token_limit")
        token_percentage = (
            (record.tokens_used / token_limit * 100) if token_limit else 0
        )

        storage_limit = quota_service.get_limit("storage_limit_mb")
        storage_percentage = (
            (record.storage_used_mb / storage_limit * 100) if storage_limit else 0
        )

        max_percentage = max(token_percentage, storage_percentage)

        if max_percentage >= 90:
            color = "danger"
        elif max_percentage >= 75:
            color = "warning"
        else:
            color = "success"

        return mark_safe(
            f'<div class="progress">'
            f'<div class="progress-bar bg-{color}" role="progressbar" '
            f'style="width: {max_percentage}%" aria-valuenow="{max_percentage}" '
            f'aria-valuemin="0" aria-valuemax="100">{max_percentage:.1f}%</div></div>'
        )

    def render_alerts(self, record):
        alert_count = QuotaAlert.objects.filter(
            tenant=record.tenant, acknowledged=False
        ).count()

        if alert_count:
            return mark_safe(
                f'<span class="badge bg-warning">{alert_count} alerts</span>'
            )
        return ""


class UsageLogTable(Table):
    timestamp = Column()
    feature = Column()
    tokens_used = Column()
    storage_delta_mb = Column(verbose_name="Storage Delta")

    class Meta:
        model = UsageLog
        template_name = "django_tables2/bootstrap5.html"
        fields = ("timestamp", "feature", "tokens_used", "storage_delta_mb")
        attrs = {"class": "table table-striped table-hover"}
        per_page = 10  # Add pagination

    def render_timestamp(self, value):
        """Format timestamp"""
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def render_storage_delta_mb(self, value):
        """Format storage value with MB unit"""
        if value is not None and value > 0:
            return f"{value:.3f} MB"
        elif value == 0:
            return "0 MB"
        return "-"

    def render_feature(self, value):
        """Format feature name"""
        return value.replace("_", " ").title()
