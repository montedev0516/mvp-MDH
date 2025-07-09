# Django Apps Overview

Below is a concise, high-level summary of the primary Django apps and their interactions.

## Tenant
- **Purpose:**  
  Manages tenants (organizations), users, and user profiles (including roles and permissions).

- **Features:**
  - Supports onboarding flows that create and configure new tenants along with their organizations and carriers.
  - Collaborates with other apps via `tenant` ForeignKey relationships that tie data (e.g., orders, dispatches, carriers) to the correct tenant.

## Dispatch
- **Purpose:**  
  Handles essential TMS (Transportation Management System) data: Orders, Dispatches, and Trips.

- **Features:**
  - Manages creation and editing of dispatch operations and tracks statuses such as “PENDING” or “INVOICED.”
  - Integrates with:
    - **Fleet** for carrier/customer details.
    - **Tenant** for ownership of dispatch objects.
    - **Subscriptions** for potential usage counts (e.g., number of orders processed).

## Subscriptions
- **Purpose:**  
  Implements subscription plans, tenant-specific subscriptions, usage quota management, and alerts (QuotaAlert).

- **Features:**
  - Ties back to tenant objects to enforce or monitor usage limits (e.g., monthly order limits, token usage).
  - Includes signals that fire when thresholds are reached, sending alerts or logging usage.

## Fleet
- **Purpose:**  
  Maintains carrier and customer entities, along with drivers, driver licenses, trucks, and trailers.

- **Features:**
  - Models often link back to `tenant` to ensure multi-tenant isolation.
  - Connects with **Dispatch** (e.g., a Trip references a carrier, truck, etc.).

## Expense
- **Purpose:**  
  Tracks expenses such as fuel or other operating costs (e.g., “Other Expense”).

- **Features:**
  - Each expense is associated with a tenant to ensure that the costing data stays scoped to the right organization.

## MDH (Django Project Config)
- **Purpose:**  
  Serves as the core folder containing Django settings, URLs, WSGI, and Celery integration.

- **Features:**
  - Coordinates app configuration, middleware, and installed apps.

## Overall Interaction
- **Tenant Ownership:**  
  Each app’s primary data models (Orders, Dispatches, Trips, Expenses) are tied to a tenant, ensuring proper multi-tenant functionality.

- **Usage Monitoring:**  
  The **Subscriptions** app monitors usage across these models and raises alerts or enforces quotas.

- **Interdependencies:**  
  - The **Fleet** app supplies carriers, drivers, and vehicles that the **Dispatch** app utilizes.
  - The **Expense** app logs cost details which are filtered by tenant.
