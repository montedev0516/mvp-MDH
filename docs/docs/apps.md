# Tenant App Documentation

## Main Models

### Tenant (`tenant/models.py`)
- Provides a top-level organization structure.
- Each tenant has a name.
- Can query its active subscription.

### Profile (`tenant/models.py`)
- Extends Django’s User model with tenant and role (admin, regular user, etc.).
- Created automatically using signals when a new User is created.

## Views for User Onboarding Flow (`tenant/views/user_management.py`)
- **UserSetupView**:  
  Guides new tenant admins through user account creation.  
  Ties in with session-based onboarding steps.
- **UserListView, UserAddView, UserEditView, UserDeleteView**:  
  Manage the user lifecycle (create, edit, delete) within a tenant or system context.

## Admin Settings (`tenant/admin.py`)
- A custom `UserAdmin` is defined that includes a `ProfileInline` to easily manage both the User and Profile.
- The `Tenant` model is registered so superusers can manage tenant data.

---

# Dispatch App Documentation

## Key Usage: Transportation Management System

### Orders, Dispatches, and Trips (`dispatch/models.py`)
- Tied to endpoints in `dispatch/views/` for creation, listing, and updating.

### OrderCreateView (`dispatch/views/order.py`)
- Handles creating new orders with file uploads (e.g., PDFs).
- Integrates with subscription usage/limit checks (e.g., counting monthly processed orders).

### Celery Tasks and Utilities (`dispatch/utils.py`)
- Contains tasks like `order_auto_extract` that parse uploaded documents asynchronously.
- Logs usage data (e.g., token counts) via the Subscriptions `QuotaService`, ensuring adherence to usage quotas and triggering alerts when necessary.

---

# Subscriptions App Documentation

## QuotaService (`subscriptions/models.py`)
- Contains the central logic for enforcing usage limits (e.g., monthly order limit, license processing limit, and token usage).
- Provides the `check_and_log_usage` feature, which can raise `ValidationError`s if a tenant’s quota is exceeded.

## Check Limit Thresholds
- `QuotaService` calls `check_limit_thresholds` to monitor when usage nears set limits.
- If thresholds are met, it generates alerts (`QuotaAlert`) that appear in the admin dashboard or usage-monitoring views.

## Usage Logging and Alerts
- **UsageLog (`subscriptions/models.py`)**:  
  Stores individual usage events (such as each order or license processed) and the associated token usage.
- **QuotaAlert (`subscriptions/models.py`)**:  
  Generated when usage approaches or exceeds specified thresholds.

---

# Fleet App Documentation

## Purpose and Scope
- Manages carriers, drivers, trucks, and driver licenses.
- Each record (Driver, DriverLicense, Truck, etc.) is associated with a tenant.

## Driver License Processing & Quotas (`fleet/utils.py`)
- **`extract_driver_license_workflow` Celery task**:  
  Processes uploaded driver licenses using AI-based extraction and logs usage (e.g., tokens, storage).
- Follows the same usage/limit approach as Dispatch by utilizing the `QuotaService` to verify license processing quotas and token usage.

## Overall Pattern
- On uploading a new driver license:
  - The Fleet app consults the Subscriptions `QuotaService` to ensure the tenant has the capacity for additional license-processing events in the current month.
  - If permitted, usage is logged.
  - If not, a `ValidationError` is raised or an alert is triggered.

---

# Integration Overview

These four apps (Tenant, Dispatch, Subscriptions, Fleet) work together to:

- **Maintain Multi-Tenant Data Isolation:**  
  Each tenant's data is segregated.
- **Monitor Usage:**  
  Usage events are logged, and quotas are enforced.
- **Enforce Subscription Policies:**  
  Integrates with Subscriptions to manage service limits.
- **Facilitate Core Operations:**  
  Supports transportation and fleet operations with a focus on scalability and governance.
