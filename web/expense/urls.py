from django.urls import path # type: ignore
from .views.expense import other as other_expense
from .views.expense.fuel import bvd as bvd_expense
from .views import payout as payout_views
from .views.expense import status as status_views

urlpatterns = [
    # Fuel expenses - BVD
    path(
        "expenses/fuel/bvd/",
        bvd_expense.BVDListView.as_view(),
        name="fuel_expense_bvd_list",
    ),
    path(
        "expenses/fuel/bvd/import/",
        bvd_expense.BVDImportView.as_view(),
        name="fuel_expense_bvd_import",
    ),
    path(
        "expenses/fuel/bvd/<uuid:pk>/",
        bvd_expense.BVDDetailView.as_view(),
        name="fuel_expense_bvd_detail",
    ),
    path(
        "expenses/fuel/bvd/<uuid:pk>/update/",
        bvd_expense.BVDUpdateView.as_view(),
        name="fuel_expense_bvd_update",
    ),
    path(
        "expenses/fuel/bvd/<uuid:pk>/delete/",
        bvd_expense.BVDDeleteView.as_view(),
        name="fuel_expense_bvd_delete",
    ),
    path(
        "expenses/fuel/bvd/search/",
        bvd_expense.BVDSearchView.as_view(),
        name="fuel_expense_bvd_search",
    ),
    path(
        "expenses/fuel/bvd/export/",
        bvd_expense.BVDExportView.as_view(),
        name="fuel_expense_bvd_export",
    ),
      
    # Other expenses
    path(
        "expense/other",
        other_expense.OtherExpenseListView.as_view(),
        name="other_expense_list",
    ),
    path(
        "expense/other/<uuid:pk>/",
        other_expense.OtherExpenseDetailView.as_view(),
        name="other_expense_detail",
    ),
    path(
        "expense/other/<uuid:pk>/update/",
        other_expense.OtherExpenseUpdateView.as_view(),
        name="other_expense_update",
    ),
    path(
        "expense/other/<uuid:pk>/delete/",
        other_expense.OtherExpenseDeleteView.as_view(),
        name="other_expense_delete",
    ),
    path(
        "expense/other/export/",
        other_expense.OtherExpenseExportView.as_view(),
        name="other_expense_export",
    ),

    # Driver Payouts
    path(
        "payout/",
        payout_views.PayoutListView.as_view(),
        name="payout_list",
    ),
    path(
        "payout/calculate/",
        payout_views.PayoutCalculateView.as_view(),
        name="payout_calculate",
    ),
    path(
        "payout/<uuid:pk>/",
        payout_views.PayoutDetailView.as_view(),
        name="payout_detail",
    ),
    path(
        "payout/<uuid:pk>/update/",
        payout_views.PayoutUpdateView.as_view(),
        name="payout_update",
    ),
    path(
        "payout/<uuid:pk>/delete/",
        payout_views.PayoutDeleteView.as_view(),
        name="payout_delete",
    ),
    path(
        "payout/<uuid:pk>/recalculate/",
        payout_views.PayoutRecalculateView.as_view(),
        name="payout_recalculate",
    ),
    path(
        "payout/<uuid:pk>/sync-status/",
        payout_views.PayoutSyncStatusView.as_view(),
        name="payout_sync_status",
    ),
    path(
        "api/payout/calculate/",
        payout_views.PayoutCalculationAPIView.as_view(),
        name="payout_calculate_api",
    ),
    
    # Status transitions
    path(
        "status/<str:model_type>/<uuid:pk>/",
        status_views.StatusTransitionView.as_view(),
        name="expense_status_transition",
    ),
    path(
        "status-options/<str:model_type>/<uuid:pk>/",
        status_views.StatusOptionsView.as_view(),
        name="expense_status_options",
    ),
]
