# tasks.py
import logging
from celery import shared_task
from django.core.management import call_command
from tenant.models import Tenant

logger = logging.getLogger("django")


@shared_task
def cleanup_incomplete_onboarding():
    try:
        logger.info("Starting cleanup task")

        # Count before cleanup
        initial_count = Tenant.objects.filter(
            # Add your filter conditions
        ).count()

        # Run cleanup
        call_command("cleanup_incomplete_onboarding")

        # Count after cleanup
        final_count = Tenant.objects.filter(
            # Add your filter conditions
        ).count()

        logger.info(
            f"Cleanup completed. Records removed: {initial_count - final_count}"
        )
        return f"Cleanup completed. Records removed: {initial_count - final_count}"
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}")
        raise
