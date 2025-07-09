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
from .views import tenant, user_management

app_name = "tenant"
urlpatterns = [
    path("about/", tenant.ProfileView.as_view(), name="about"),
    path("contact/", tenant.ProfileView.as_view(), name="contact"),
    path("privacy/", tenant.ProfileView.as_view(), name="privacy"),
    path("faq/", tenant.ProfileView.as_view(), name="faq"),
    path("profile/", tenant.ProfileView.as_view(), name="profile"),
    path("login/", tenant.login_view, name="login"),
    path("logout/", tenant.logout_view, name="logout"),
    path(
        "user-management/onboarding/",
        user_management.OnboardingWizardView.as_view(),
        name="onboarding",
    ),
    path(
        "user-management/organization-setup/",
        user_management.OrganizationSetupView.as_view(),
        name="organization_setup",
    ),
    path(
        "user-management/carrier-setup/",
        user_management.CarrierSetupView.as_view(),
        name="carrier_setup",
    ),
    path(
        "user-management/add/",
        user_management.UserAddView.as_view(),
        name="user_add",
    ),
    path(
        "user-management/user-setup/",
        user_management.UserSetupView.as_view(),
        name="user_setup",
    ),
    path(
        "user-management/users/",
        user_management.UserListView.as_view(),
        name="user_list",
    ),
    path(
        "user-management/users/<int:pk>/edit/",
        user_management.UserEditView.as_view(),
        name="user_edit",
    ),
    path(
        "user-management/users/<int:pk>/delete/",
        user_management.UserDeleteView.as_view(),
        name="user_delete",
    ),
    path("", tenant.TenantHome.as_view(), name="home"),
]
