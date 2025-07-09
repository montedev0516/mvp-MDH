# subscriptions/models.py
import logging
from uuid import uuid4
from datetime import datetime
from django.utils import timezone
from typing import Tuple, Optional
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model

logger = logging.getLogger("django")


class AlertType(models.TextChoices):
    WARNING = "warning", "Warning"  # 80% threshold
    CRITICAL = "critical", "Critical"  # 90% threshold
    EXCEEDED = "exceeded", "Exceeded"  # 100% threshold


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class SubscriptionPlan(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField()
    max_active_drivers = models.IntegerField(validators=[MinValueValidator(0)])
    max_active_trucks = models.IntegerField(validators=[MinValueValidator(0)])
    max_organizations = models.IntegerField(validators=[MinValueValidator(0)])
    monthly_order_limit = models.IntegerField(validators=[MinValueValidator(0)])
    monthly_license_limit = models.IntegerField(validators=[MinValueValidator(0)])
    monthly_token_limit = models.IntegerField(validators=[MinValueValidator(0)])
    storage_limit_mb = models.IntegerField(validators=[MinValueValidator(0)])
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2)
    is_custom = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} Plan"


class TenantSubscription(BaseModel):
    tenant = models.ForeignKey(
        "tenant.Tenant", on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=True)
    billing_cycle = models.CharField(
        max_length=20,
        choices=[("monthly", "Monthly"), ("yearly", "Yearly")],
        default="monthly",
    )

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "is_active", "start_date", "end_date"])
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.plan.name}"


class TenantCustomQuota(BaseModel):
    tenant = models.OneToOneField("tenant.Tenant", on_delete=models.CASCADE)
    max_active_drivers = models.IntegerField(null=True, blank=True)
    max_active_trucks = models.IntegerField(null=True, blank=True)
    max_organizations = models.IntegerField(null=True, blank=True)
    monthly_order_limit = models.IntegerField(null=True, blank=True)
    monthly_license_limit = models.IntegerField(null=True, blank=True)
    monthly_token_limit = models.IntegerField(null=True, blank=True)
    storage_limit_mb = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"Custom Quota - {self.tenant.name}"


class UsagePeriod(BaseModel):
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    orders_processed = models.IntegerField(default=0)
    licenses_processed = models.IntegerField(default=0)
    tokens_used = models.IntegerField(default=0)
    storage_used_mb = models.IntegerField(default=0)

    class Meta:
        unique_together = [("tenant", "start_date", "end_date")]
        indexes = [
            models.Index(fields=["tenant", "start_date", "end_date"]),
        ]


class UsageLog(BaseModel):
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)
    usage_period = models.ForeignKey(UsagePeriod, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    feature = models.CharField(max_length=50)
    tokens_used = models.IntegerField(default=0)
    storage_delta_mb = models.FloatField(default=0.0)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()

    def __str__(self):
        return f"{self.tenant.name} - {self.feature} - {self.timestamp}"


class QuotaAlert(BaseModel):
    tenant = models.ForeignKey("tenant.Tenant", on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    feature = models.CharField(max_length=50)  # e.g., 'storage', 'tokens', 'orders'
    threshold_percentage = models.IntegerField()
    message = models.TextField()
    acknowledged = models.BooleanField(default=False)
    acknowledged_by = models.ForeignKey(
        get_user_model(), on_delete=models.SET_NULL, null=True, blank=True
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-notified_at"]
        indexes = [
            models.Index(fields=["tenant", "alert_type", "feature"]),
            models.Index(fields=["acknowledged", "notified_at"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.feature} at {self.threshold_percentage}%"


class QuotaService:
    def __init__(self, tenant):
        self.tenant = tenant
        self._subscription = None
        self._custom_quota = None
        self._usage_period = None

    @property
    def subscription(self):
        if not self._subscription:
            self._subscription = (
                TenantSubscription.objects.filter(tenant=self.tenant, is_active=True)
                .select_related("plan")
                .first()
            )

            if not self._subscription:
                raise ValidationError("No active subscription found for tenant")

        return self._subscription

    @property
    def custom_quota(self):
        if self._custom_quota is None:  # Note: using None for cache miss
            self._custom_quota = TenantCustomQuota.objects.filter(
                tenant=self.tenant
            ).first()

        return self._custom_quota

    @property
    def usage_period(self):
        if not self._usage_period:
            self._usage_period = self._get_or_create_usage_period()
        return self._usage_period

    def _get_or_create_usage_period(self):
        """Get or create usage period for current billing cycle"""
        now = timezone.now()

        # Calculate period dates based on billing cycle
        if self.subscription.billing_cycle == "monthly":
            start_date = datetime(now.year, now.month, 1)
            if now.month == 12:
                end_date = datetime(now.year + 1, 1, 1)
            else:
                end_date = datetime(now.year, now.month + 1, 1)
        else:  # yearly
            start_date = datetime(now.year, 1, 1)
            end_date = datetime(now.year + 1, 1, 1)

        usage_period, _ = UsagePeriod.objects.get_or_create(
            tenant=self.tenant, start_date=start_date, end_date=end_date
        )

        return usage_period

    def get_limit(self, quota_type: str) -> int:
        """Get effective limit for a quota type, considering custom quotas"""
        if self.custom_quota:
            custom_value = getattr(self.custom_quota, quota_type, None)
            if custom_value is not None:
                return custom_value

        return getattr(self.subscription.plan, quota_type)

    def check_and_log_usage(
        self,
        feature: str,
        tokens: int = 0,
        storage_mb: int = 0,
        related_object: Optional[models.Model] = None,
    ) -> Tuple[bool, str]:
        """
        Check if usage is allowed and log it if it is
        Returns (allowed, message)
        """
        try:
            # Check relevant quotas based on feature
            if feature == "order_processing":
                if not self._check_order_quota():
                    return False, "Monthly order processing limit exceeded"

            elif feature == "license_processing":
                if not self._check_license_quota():
                    return False, "Monthly license processing limit exceeded"

            # Check token quota
            if tokens > 0 and not self._check_token_quota(tokens):
                return False, "Monthly token limit exceeded"

            # Check storage quota
            if storage_mb > 0 and not self._check_storage_quota(storage_mb):
                return False, "Storage limit exceeded"

            # If we got here, usage is allowed - log it
            self._log_usage(feature, tokens, storage_mb, related_object)

            return True, "Usage allowed"

        except Exception as e:
            logger.error(f"Error checking quotas: {str(e)}", exc_info=True)
            return False, f"Error checking quotas: {str(e)}"

    def _check_order_quota(self) -> bool:
        limit = self.get_limit("monthly_order_limit")
        current = self.usage_period.orders_processed
        return current < limit

    def _check_license_quota(self) -> bool:
        limit = self.get_limit("monthly_license_limit")
        current = self.usage_period.licenses_processed
        return current < limit

    def _check_token_quota(self, additional_tokens: int) -> bool:
        limit = self.get_limit("monthly_token_limit")
        current = self.usage_period.tokens_used
        return (current + additional_tokens) <= limit

    def _check_storage_quota(self, additional_mb: int) -> bool:
        limit = self.get_limit("storage_limit_mb")
        current = self.usage_period.storage_used_mb
        return (current + additional_mb) <= limit

    def _log_usage(
        self,
        feature: str,
        tokens: int,
        storage_mb: int,
        related_object: Optional[models.Model],
    ):
        """Log usage and update period totals"""
        # Create usage log
        usage_log = UsageLog(
            tenant=self.tenant,
            usage_period=self.usage_period,
            feature=feature,
            tokens_used=tokens,
            storage_delta_mb=storage_mb,
        )

        # Add reference to related object if provided
        if related_object:
            usage_log.content_type = ContentType.objects.get_for_model(related_object)
            usage_log.object_id = related_object.id

        usage_log.save()

        # Update period totals
        if feature == "order_processing":
            self.usage_period.orders_processed += 1
        elif feature == "license_processing":
            self.usage_period.licenses_processed += 1

        self.usage_period.tokens_used += tokens
        self.usage_period.storage_used_mb += storage_mb
        self.usage_period.save()

    def check_limit_thresholds(self):
        """Check if any quotas are approaching limits and create alerts"""
        thresholds = [80, 90, 95]  # Percentage thresholds for alerts

        for quota_type in [
            "monthly_order_limit",
            "monthly_license_limit",
            "monthly_token_limit",
            "storage_limit_mb",
        ]:
            limit = self.get_limit(quota_type)

            # Get current usage
            if quota_type == "monthly_order_limit":
                current = self.usage_period.orders_processed
            elif quota_type == "monthly_license_limit":
                current = self.usage_period.licenses_processed
            elif quota_type == "monthly_token_limit":
                current = self.usage_period.tokens_used
            else:  # storage_limit_mb
                current = self.usage_period.storage_used_mb

            # Check each threshold
            for threshold in thresholds:
                if (current / limit * 100) >= threshold:
                    # Create alert if one doesn't exist for this threshold
                    QuotaAlert.objects.get_or_create(
                        tenant=self.tenant,
                        alert_type="approaching",
                        feature=quota_type,
                        threshold_percentage=threshold,
                        defaults={"acknowledged": False},
                    )
