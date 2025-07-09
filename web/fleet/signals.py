from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from fleet.models.driver import Driver, DriverLicense
from fleet.models.truck import Truck
from fleet.models.carrier import Carrier
from fleet.utils import format_phone_number, format_license_number, validate_vin


@receiver(pre_save, sender=Driver)
def driver_pre_save(sender, instance, **kwargs):
    """Pre-save signal for Driver model"""
    if instance.phone:
        instance.phone = format_phone_number(instance.phone)
    if instance.license_number:
        instance.license_number = format_license_number(instance.license_number)


@receiver(pre_save, sender=DriverLicense)
def driver_license_pre_save(sender, instance, **kwargs):
    """Pre-save signal for DriverLicense model"""
    if instance.license_number:
        instance.license_number = format_license_number(instance.license_number)


@receiver(pre_save, sender=Truck)
def truck_pre_save(sender, instance, **kwargs):
    """Pre-save signal for Truck model"""
    # Auto-generate trailer number if is_trailer is True
    if instance.is_trailer and not instance.trailer_number:
        instance.trailer_number = str(instance.unit)
    
    # Validate VIN
    if instance.vin and not validate_vin(instance.vin):
        raise ValueError("Invalid VIN number")


@receiver(pre_save, sender=Carrier)
def carrier_pre_save(sender, instance, **kwargs):
    """Pre-save signal for Carrier model"""
    if instance.phone:
        instance.phone = format_phone_number(instance.phone)


@receiver(post_save, sender=Driver)
def driver_post_save(sender, instance, created, **kwargs):
    """Post-save signal for Driver model"""
    if created:
        # Additional setup for new drivers
        pass


@receiver(post_save, sender=Truck)
def truck_post_save(sender, instance, created, **kwargs):
    """Post-save signal for Truck model"""
    if created:
        # Update carrier's total trucks count
        if instance.carrier:
            instance.carrier.total_trucks = Truck.objects.filter(
                carrier=instance.carrier,
                is_active=True
            ).count()
            instance.carrier.save()


@receiver(pre_delete, sender=Truck)
def truck_pre_delete(sender, instance, **kwargs):
    """Pre-delete signal for Truck model"""
    # Update carrier's total trucks count
    if instance.carrier:
        instance.carrier.total_trucks = Truck.objects.filter(
            carrier=instance.carrier,
            is_active=True
        ).exclude(pk=instance.pk).count()
        instance.carrier.save() 