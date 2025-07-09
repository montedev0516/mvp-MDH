"""
URL configuration for mdh project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path
from fleet.views.driver import (
    DriverView,
    DriverCreateView,
    DriverUpdateView,
    DriverDeleteView,
    DriverDetailView,
)
from fleet.views.driver_license import (
    DriverLicenseListView,
    DriverLicenseDetailView,
    DriverLicenseUpdateView,
    DriverLicenseDeleteView,
)
from fleet.views.driver_common import DriverLicenseUploadView
from fleet.views.truck import (
    TruckListView,
    TruckDetailView,
    TruckCreateView,
    TruckUpdateView,
    TruckDeleteView,
)

from fleet.views.carrier import (
    CarrierListView,
    CarrierDetailView,
    CarrierCreateView,
    CarrierUpdateView,
    CarrierDeleteView,
)

app_name = "fleet"

urlpatterns = [
    # Drivers
    path("drivers/", DriverView.as_view(), name="driver-list"),
    path("drivers/create/", DriverCreateView.as_view(), name="driver-create"),
    path("drivers/<uuid:pk>/", DriverDetailView.as_view(), name="driver-detail"),
    path("drivers/<uuid:pk>/update/", DriverUpdateView.as_view(), name="driver-update"),
    path("drivers/<uuid:pk>/delete/", DriverDeleteView.as_view(), name="driver-delete"),
    
    # Driver Licenses
    path("driver-licenses/", DriverLicenseListView.as_view(), name="driver-license-list"),
    path("driver-licenses/<uuid:pk>/", DriverLicenseDetailView.as_view(), name="driver-license-detail"),
    path("driver-licenses/<uuid:pk>/update/", DriverLicenseUpdateView.as_view(), name="driver-license-update"),
    path("driver-licenses/<uuid:pk>/delete/", DriverLicenseDeleteView.as_view(), name="driver-license-delete"),
    path("driver-licenses/upload/", DriverLicenseUploadView.as_view(), name="driver-license-upload"),
    
    # Trucks
    path("trucks/", TruckListView.as_view(), name="truck-list"),
    path("trucks/create/", TruckCreateView.as_view(), name="truck-create"),
    path("trucks/<uuid:pk>/", TruckDetailView.as_view(), name="truck-detail"),
    path("trucks/<uuid:pk>/update/", TruckUpdateView.as_view(), name="truck-update"),
    path("trucks/<uuid:pk>/delete/", TruckDeleteView.as_view(), name="truck-delete"),
    
    # Carriers
    path("carriers/", CarrierListView.as_view(), name="carrier-list"),
    path("carriers/create/", CarrierCreateView.as_view(), name="carrier-create"),
    path("carriers/<uuid:pk>/", CarrierDetailView.as_view(), name="carrier-detail"),
    path("carriers/<uuid:pk>/update/", CarrierUpdateView.as_view(), name="carrier-update"),
    path("carriers/<uuid:pk>/delete/", CarrierDeleteView.as_view(), name="carrier-delete"),
]
