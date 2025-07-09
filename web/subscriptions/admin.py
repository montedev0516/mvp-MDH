from django.contrib import admin
from .models import (
    SubscriptionPlan,
    TenantSubscription,
    TenantCustomQuota,
    UsagePeriod,
    UsageLog,
    QuotaAlert,
)


admin.site.register(SubscriptionPlan)
admin.site.register(TenantSubscription)
admin.site.register(TenantCustomQuota)
admin.site.register(UsagePeriod)
admin.site.register(UsageLog)
admin.site.register(QuotaAlert)
