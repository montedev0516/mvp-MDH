# tenant/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from models.models import BaseModel


class Role(models.TextChoices):
    REGULAR_USER = "regular_user", "Regular User"
    ADMIN = "admin", "Admin"
    SUPER_ADMIN = "super_admin", "Super Admin"


class Tenant(BaseModel):
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return f"{self.name}"

    def get_active_subscription(self):
        """Get the current active subscription for this tenant"""
        from django.utils import timezone
        from subscriptions.models import TenantSubscription

        return TenantSubscription.objects.filter(
            tenant=self,
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gt=timezone.now(),
        ).first()

    @property
    def current_subscription(self):
        """Property to get current active subscription"""
        return self.get_active_subscription()


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.REGULAR_USER
    )

    def __str__(self) -> str:
        return f"{self.user.username} {self.user.email}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Check if a tenant was specified during user creation
        tenant = getattr(instance, "_tenant", None)

        if not tenant:
            # Use default tenant as fallback
            tenant = Tenant.objects.filter(name="default").first()
            if not tenant:
                tenant = Tenant.objects.create(name="default")

        Profile.objects.create(user=instance, tenant=tenant)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
