import logging
from django.db.models.signals import post_save
from django.db import models
from django.dispatch import receiver

from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from .models import (
    SubscriptionPlan,
    TenantSubscription,
    QuotaService,
    UsageLog,
    QuotaAlert,
)
from dispatch.models import Order, UploadFile
from fleet.models import Carrier, Driver, Truck, DriverLicense

logger = logging.getLogger("django")


def calculate_file_size_mb(file_content) -> float:
    """Calculate file size in megabytes with precision"""
    try:
        size_in_bytes = len(file_content.encode("utf-8"))
        return round(size_in_bytes / (1024 * 1024), 3)
    except Exception as e:
        logger.error(f"Error calculating file size: {str(e)}", exc_info=True)
        return 0


def check_quota_thresholds(tenant, usage_period, request=None):
    """
    Check quotas and create alerts with messages
    Args:
        tenant: Tenant instance
        usage_period: Current usage period
        request: HTTP request object (for messages)
    """
    quota_service = QuotaService(tenant)
    thresholds = {
        80: ("warning", "Warning"),
        90: ("error", "Critical"),
        100: ("error", "Exceeded"),
    }

    quotas_to_check = {
        "monthly_order_limit": (usage_period.orders_processed, "Order Processing"),
        "monthly_license_limit": (
            usage_period.licenses_processed,
            "License Processing",
        ),
        "monthly_token_limit": (usage_period.tokens_used, "API Token"),
        "storage_limit_mb": (usage_period.storage_used_mb, "Storage"),
    }

    for quota_type, (current_usage, display_name) in quotas_to_check.items():
        limit = quota_service.get_limit(quota_type)
        if limit > 0:
            usage_percentage = (current_usage / limit) * 100

            for threshold, (message_level, alert_type) in thresholds.items():
                if usage_percentage >= threshold:
                    alert, created = QuotaAlert.objects.get_or_create(
                        tenant=tenant,
                        feature=quota_type,
                        threshold_percentage=threshold,
                        defaults={
                            "alert_type": alert_type,
                            "message": f"{display_name} quota usage has reached {threshold:.1f}%",
                        },
                    )

                    # Send message if request object is available
                    if created and request:
                        if message_level == "warning":
                            messages.warning(
                                request,
                                f"{display_name} quota usage has reached {threshold:.1f}%. "
                                f"Current usage: {current_usage:.1f}/{limit}",
                            )
                        else:
                            messages.error(
                                request,
                                f"{display_name} quota limit {alert_type}! "
                                f"Current usage: {current_usage:.1f}/{limit}",
                            )


def check_quota_signal(sender, instance, **kwargs):
    """Signal handler to check quotas before saving objects"""
    if not hasattr(instance, "tenant"):
        return

    # Skip quota check for models that are handled by celery tasks
    if isinstance(instance, (Order, DriverLicense)):
        # Only check storage limit on initial creation
        if not instance.pk:  # New instance
            quota_service = QuotaService(instance.tenant)
            current_storage = quota_service.usage_period.storage_used_mb
            storage_limit = quota_service.get_limit("storage_limit_mb")

            if current_storage > storage_limit:
                raise ValidationError("Storage limit exceeded")
        # Skip creating usage log here as it will be handled by celery task
        return

    # For other models, proceed with normal quota checking
    if isinstance(instance, Carrier):
        if not instance.pk:  # Only check on creation
            allowed, message = instance.tenant.check_quota("organization")
            if not allowed:
                raise ValidationError(message)

    elif isinstance(instance, Driver):
        if not instance.pk and instance.still_working:
            allowed, message = instance.carrier.tenant.check_quota("driver")
            if not allowed:
                raise ValidationError(message)

    elif isinstance(instance, Truck):
        if not instance.pk:
            allowed, message = instance.carrier.tenant.check_quota("truck")
            if not allowed:
                raise ValidationError(message)

    elif isinstance(instance, UploadFile):
        if not instance.pk:
            file_size_mb = calculate_file_size_mb(instance.file)
            allowed, message = instance.tenant.check_quota(
                "storage", amount=file_size_mb
            )
            if not allowed:
                raise ValidationError(message)

            # Log file upload usage
            quota_service = QuotaService(instance.tenant)
            _ = UsageLog.objects.create(
                tenant=instance.tenant,
                usage_period=quota_service.usage_period,
                feature="file_upload",
                storage_delta_mb=file_size_mb,
                content_type=ContentType.objects.get_for_model(UploadFile),
                object_id=instance.id,
            )

            # Update usage period
            quota_service.usage_period.storage_used_mb += file_size_mb
            quota_service.usage_period.save()

            # Check thresholds
            check_quota_thresholds(instance.tenant, quota_service.usage_period)


@receiver(post_save, sender="tenant.Tenant")
def create_default_subscription(sender, instance, created, **kwargs):
    """Create default subscription for new tenants"""
    if created:
        # Avoid circular import
        from tenant.models import Tenant

        if isinstance(instance, Tenant) and not hasattr(
            instance, "_subscription_creating"
        ):
            # Get or create the default plan
            default_plan = SubscriptionPlan.objects.filter(name="Basic").first()
            if not default_plan:
                default_plan = SubscriptionPlan.objects.create(
                    name="Basic",
                    description="Basic subscription plan",
                    max_active_drivers=10,
                    max_active_trucks=10,
                    max_organizations=1,
                    monthly_order_limit=50,
                    monthly_license_limit=10,
                    monthly_token_limit=10000,
                    storage_limit_mb=1024,  # 1GB
                    price_monthly=0,  # Free tier
                    price_yearly=0,
                )

            try:
                # Set flag to prevent recursive signal
                instance._subscription_creating = True

                TenantSubscription.objects.create(
                    tenant=instance,
                    plan=default_plan,
                    start_date=timezone.now(),
                    end_date=timezone.now() + timedelta(days=30),  # 30-day trial
                    is_active=True,
                    auto_renew=False,
                )
            finally:
                # Clean up flag
                delattr(instance, "_subscription_creating")


# Connect signals
models.signals.pre_save.connect(check_quota_signal, sender=Order)
models.signals.pre_save.connect(check_quota_signal, sender=DriverLicense)
models.signals.pre_save.connect(check_quota_signal, sender=Carrier)
models.signals.pre_save.connect(check_quota_signal, sender=Driver)
models.signals.pre_save.connect(check_quota_signal, sender=Truck)
models.signals.pre_save.connect(check_quota_signal, sender=UploadFile)
