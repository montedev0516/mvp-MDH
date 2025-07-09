from django.core.exceptions import ValidationError
from django.http import HttpRequest
import math
from subscriptions.models import QuotaService


class StorageQuotaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        # Only check quotas for file uploads
        if request.method == "POST" and request.FILES:
            if not hasattr(request, "tenant"):
                return self.get_response(request)

            quota_service = QuotaService(request.tenant)

            # Calculate total upload size in MB
            total_size_mb = sum(
                math.ceil(f.size / (1024 * 1024))  # Round up to nearest MB
                for f in request.FILES.values()
            )

            # Check if upload would exceed quota
            allowed, message = quota_service.check_and_log_usage(
                feature="file_upload", storage_mb=total_size_mb
            )

            if not allowed:
                raise ValidationError(message)

        return self.get_response(request)
