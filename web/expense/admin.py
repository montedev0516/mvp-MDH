from django.contrib import admin  # type: ignore
from expense.models import BVD, OtherExpense, Payout
from django.core.exceptions import ValidationError
from expense.models import PayoutStatus


# Register your models here.
@admin.register(BVD)
class BVDAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "company_name",
        "unit",
        "quantity",
        "amount",
        "status",
    )
    list_filter = ("company_name", "status", "tenant")
    search_fields = (
        "company_name",
        "card_number",
        "driver__first_name",
        "driver__last_name",
        "site_name",
        "site_city",
    )
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        """Ensure tenant filtering works correctly in admin"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "profile") and request.user.profile.tenant:
            return qs.filter(tenant=request.user.profile.tenant)
        return qs.none()

    def save_model(self, request, obj, form, change):
        """Auto-assign tenant if not specified"""
        if not change and not obj.tenant_id and hasattr(request.user, "profile"):
            obj.tenant = request.user.profile.tenant
        super().save_model(request, obj, form, change)


@admin.register(OtherExpense)
class OtherExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "name",
        "category",
        "amount",
        "currency",
        "driver",
        "truck",
        "status",
        "reimbursement_status"
    )
    list_filter = (
        "status",
        "category",
        "currency",
        "reimbursement_status",
        "driver",
        "truck",
        "tenant"
    )
    search_fields = (
        "name",
        "description",
        "vendor_name",
        "driver__first_name",
        "driver__last_name",
        "truck__unit"
    )
    date_hierarchy = "date"
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        """Ensure tenant filtering works correctly in admin"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "profile") and request.user.profile.tenant:
            return qs.filter(tenant=request.user.profile.tenant)
        return qs.none()

    def save_model(self, request, obj, form, change):
        """Auto-assign tenant if not specified"""
        if not change and not obj.tenant_id and hasattr(request.user, "profile"):
            obj.tenant = request.user.profile.tenant
        super().save_model(request, obj, form, change)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        "driver",
        "from_date",
        "to_date", 
        "status",
        "final_cad_amount",
        "final_usd_amount",
        "exchange_rate",
        "created_at"
    )
    list_filter = (
        "status",
        "driver",
        "tenant",
        "from_date",
        "created_at"
    )
    search_fields = (
        "driver__first_name",
        "driver__last_name", 
        "driver__email"
    )
    date_hierarchy = "from_date"
    readonly_fields = (
        "created_at", 
        "updated_at",
        "cad_revenue",
        "cad_commission", 
        "cad_expenses",
        "cad_payout",
        "usd_revenue",
        "usd_commission",
        "usd_expenses", 
        "usd_payout"
    )
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("driver", "tenant", "from_date", "to_date", "status")
        }),
        ("CAD Calculations", {
            "fields": ("cad_revenue", "cad_commission", "cad_expenses", "cad_payout"),
            "classes": ("collapse",)
        }),
        ("USD Calculations", {
            "fields": ("usd_revenue", "usd_commission", "usd_expenses", "usd_payout"),
            "classes": ("collapse",)
        }),
        ("Final Amounts", {
            "fields": ("exchange_rate", "final_cad_amount", "final_usd_amount")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        })
    )
    
    filter_horizontal = ("bvd_expenses", "other_expenses")

    def get_queryset(self, request):
        """Ensure tenant filtering works correctly in admin"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "profile") and request.user.profile.tenant:
            return qs.filter(tenant=request.user.profile.tenant)
        return qs.none()

    def save_model(self, request, obj, form, change):
        """Auto-assign tenant if not specified"""
        if not change and not obj.tenant_id and hasattr(request.user, "profile"):
            obj.tenant = request.user.profile.tenant
        super().save_model(request, obj, form, change)
        
    actions = ["recalculate_payouts", "mark_as_processing", "mark_as_completed"]
    
    def recalculate_payouts(self, request, queryset):
        """Admin action to recalculate selected payouts"""
        updated = 0
        for payout in queryset.filter(status=PayoutStatus.DRAFT):
            payout.calculate_totals()
            payout.save()
            updated += 1
        self.message_user(request, f"Recalculated {updated} payouts")
    recalculate_payouts.short_description = "Recalculate selected payouts"
    
    def mark_as_processing(self, request, queryset):
        """Admin action to mark payouts as processing"""
        updated = 0
        for payout in queryset.filter(status=PayoutStatus.DRAFT):
            try:
                payout.update_status(PayoutStatus.PROCESSING, request.user)
                updated += 1
            except ValidationError:
                pass  # Skip invalid transitions
        self.message_user(request, f"Marked {updated} payouts as processing")
    mark_as_processing.short_description = "Mark as Processing"
    
    def mark_as_completed(self, request, queryset):
        """Admin action to mark payouts as completed"""
        updated = 0
        for payout in queryset.filter(status=PayoutStatus.PROCESSING):
            try:
                payout.update_status(PayoutStatus.COMPLETED, request.user)
                updated += 1
            except ValidationError:
                pass  # Skip invalid transitions
        self.message_user(request, f"Marked {updated} payouts as completed")
    mark_as_completed.short_description = "Mark as Completed"



    
