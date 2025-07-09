"""URL configuration for the dispatch app."""

from django.urls import path
from . import views
from .views import api
from .views.api import available_assignments, available_resources
from .views.assignment import (
    AssignmentListView,
    AssignmentDetailView,
    AssignmentCreateView,
    AssignmentUpdateView,
    AssignmentDeleteView,
    get_dispatch_details
)

app_name = 'dispatch'

urlpatterns = [
    # Order URLs
    path('orders/', views.OrderListView.as_view(), name='order_list'),
    path('orders/create/', views.OrderCreateView.as_view(), name='order_create'),
    path('orders/<uuid:pk>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('orders/<uuid:pk>/edit/', views.OrderEditView.as_view(), name='order_edit'),
    path('orders/<uuid:pk>/delete/', views.OrderDeleteView.as_view(), name='order_delete'),
    path('orders/<uuid:pk>/upload/', views.OrderFileUploadView.as_view(), name='order_upload'),
    path('orders/<uuid:pk>/download/', views.OrderFileDownloadView.as_view(), name='order_download'),
    path('orders/<uuid:pk>/pdf/', views.OrderPDFView.as_view(), name='order_pdf'),
    
    # Trip URLs
    path('trips/', views.TripListView.as_view(), name='trip_list'),
    path('trips/create/', views.TripCreateView.as_view(), name='trip_create'),
    path('trips/<uuid:pk>/', views.TripDetailView.as_view(), name='trip_detail'),
    path('trips/<uuid:pk>/edit/', views.TripUpdateView.as_view(), name='trip_edit'),
    path('trips/<uuid:pk>/delete/', views.TripDeleteView.as_view(), name='trip_delete'),
    path('orders/<uuid:order_id>/trips/create/', views.TripCreateView.as_view(), name='order_trip_create'),
    
    # Dispatch URLs
    path('', views.DispatchListView.as_view(), name='dispatch_list'),
    path('create/<uuid:order_pk>/', views.DispatchCreateView.as_view(), name='dispatch_create'),
    path('<uuid:pk>/', views.DispatchDetailView.as_view(), name='dispatch_detail'),
    path('<uuid:pk>/update/', views.DispatchUpdateView.as_view(), name='dispatch_update'),
    path('<uuid:pk>/delete/', views.DispatchDeleteView.as_view(), name='dispatch_delete'),
    path('<uuid:pk>/invoice/', views.DispatchInvoiceView.as_view(), name='dispatch_invoice'),
    
    # Assignment URLs
    path('assignments/', AssignmentListView.as_view(), name='assignment-list'),
    path('assignments/create/', AssignmentCreateView.as_view(), name='assignment-create'),
    path('assignments/<uuid:pk>/', AssignmentDetailView.as_view(), name='assignment-detail'),
    path('assignments/<uuid:pk>/edit/', AssignmentUpdateView.as_view(), name='assignment-update'),
    path('assignments/<uuid:pk>/delete/', AssignmentDeleteView.as_view(), name='assignment-delete'),
    
    # AJAX endpoints
    path('assignment/get-dispatch-details/', get_dispatch_details, name='get-dispatch-details'),
    
    # API Endpoints
    path('api/assignments/available/', available_assignments, name='api_available_assignments'),
    path('api/assignments/available-resources/', available_resources, name='api_available_resources'),
    path('api/orders/extract/', api.order_extract, name='api_order_extract'),
    path('api/orders/validate/', api.order_validate, name='api_order_validate'),
    path('api/trips/status/', api.trip_status_update, name='api_trip_status_update'),
    path('api/assignments/status/', api.assignment_status_update, name='api_assignment_status_update'),
]
