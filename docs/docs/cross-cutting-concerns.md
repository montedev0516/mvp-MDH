# Project Cross-Cutting Concerns

## File Uploads
- **Centralized Handling:**  
  The `OrderCreateView.handle_uploaded_file` method checks quotas (`storage_limit_mb`, `monthly_order_limit`) for each file.
- **Celery Task Processing:**  
  The `order_auto_extract` Celery task processes uploaded files and enforces storage and token usage limits.

## Quota & Usage Logging
- **Integration Across Apps:**  
  Multiple apps (e.g., `dispatch`, `fleet`, `subscriptions`) integrate with `QuotaService` to track usage.
- **Usage Logging:**  
  Logs are recorded in `UsageLog` whenever new files or data are processed.
- **Alerts:**  
  The `check_limit_thresholds` mechanism raises alerts when usage approaches or exceeds set thresholds.

## Templates
- **Common UI Patterns:**  
  Templates like `upload.html` and `create.html` implement shared UI patterns.
- **Reusable Partials:**  
  Partials (e.g., `partials/pdfjs/viewer.html`) ensure consistent file upload previews and PDF viewing across the codebase.

## Celery & Task Flows
**Monitor Celery tasks (e.g., `order_auto_extract`) through:**

- **Flower**: `celery -A mdh flower` in [compose.yaml](../../compose.yaml) for real-time task monitoring.
- **Django Admin**: Check stuck or failed tasks in the admin logs.

**Scaling & Concurrency**:

- Adjust worker concurrency in [compose.yaml](../../compose.yaml) via the `command` or `environment` settings.
- Increase worker replicas or autoscaling if tasks (e.g., document extractions) spike in volume.

## S3/Storage Uploads

The code frequently references uploading files to **S3** (in both `OrderCreateView` and `DriverLicenseUploadView`). Developers may want to confirm credentials and test those flows locally (or with a mock S3) to ensure everything works before production.
