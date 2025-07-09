from django.urls import path
from .views import (
    SubscriptionPlanListView,
    SubscriptionPlanCreateView,
    SubscriptionPlanUpdateView,
    SubscriptionPlanDeleteView,
    TenantSubscriptionListView,
    SubscriptionUpdateView,
    UsageMonitoringView,
    TenantUsageDetailView,
    acknowledge_alert,
)

app_name = "subscriptions"

urlpatterns = [
    # Subscription Plans
    path("plans/", SubscriptionPlanListView.as_view(), name="plan_list"),
    path(
        "plans/create/",
        SubscriptionPlanCreateView.as_view(),
        name="plan_create",
    ),
    path(
        "plans/<uuid:pk>/update/",
        SubscriptionPlanUpdateView.as_view(),
        name="plan_update",
    ),
    path(
        "plans/<uuid:pk>/delete/",
        SubscriptionPlanDeleteView.as_view(),
        name="plan_delete",
    ),
    # Usage Monitoring
    path("usage/", UsageMonitoringView.as_view(), name="usage_monitoring"),
    path(
        "usage/<uuid:pk>/", TenantUsageDetailView.as_view(), name="tenant_usage_detail"
    ),
    # API Endpoints
    path(
        "api/alerts/<uuid:pk>/acknowledge/", acknowledge_alert, name="acknowledge_alert"
    ),
    # Tenant Subscriptions
    path(
        "<uuid:pk>/update/",
        SubscriptionUpdateView.as_view(),
        name="tenant_subscription_update",
    ),
    path(
        "",
        TenantSubscriptionListView.as_view(),
        name="tenant_subscription_list",
    ),
]
