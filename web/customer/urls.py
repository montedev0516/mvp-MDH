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
from customer.views import (
    CustomerListView,
    CustomerDetailView,
    CustomerUpdateView,
    CustomerDeleteView,
    CustomerCreateView,
)

urlpatterns = [
    path("", CustomerListView.as_view(), name="customer_list"),
    path("create/", CustomerCreateView.as_view(), name="customer_create"),
    path("<uuid:pk>/", CustomerDetailView.as_view(), name="customer_detail"),
    path(
        "<uuid:pk>/update/",
        CustomerUpdateView.as_view(),
        name="customer_update",
    ),
    path(
        "<uuid:pk>/delete/",
        CustomerDeleteView.as_view(),
        name="customer_delete",
    ),
]
