# Advanced Usage, Developer Workflows & Best Practices

---

## 1. Detailed Explanations of Core Functions & APIs

### Tenant & User Onboarding
- **UserSetupView**  
  Guides a new tenant admin through initialization steps. Includes user creation, tenant registration, and linking existing carriers or customers.
- **Profile**  
  Extends Django’s User model with a tenant field and role-based logic.

### Order Management & File Extraction (Dispatch)
- **OrderCreateView**  
  Responsible for creating orders, validating usage quotas, handling PDF uploads, and triggering Celery tasks for auto-extraction.
- **order_auto_extract**  
  The Celery task analyzing uploaded documents, logging usage to Subscriptions, and sending alerts for over-limit usage.

### Usage & Quota Enforcement (Subscriptions)
- **QuotaService**  
  Provides `check_and_log_usage` to see if a tenant’s limit is exceeded.
- **check_limit_thresholds**  
  Dispatches alerts if usage is approaching a configurable threshold.

### Fleet & Driver Licensing
- **extract_driver_license_workflow**  
  Demonstrates the same usage logging pattern as Orders. Calls Subscriptions to confirm capacity, and processes driver license documents with AI-based extraction if allowed.

### Extensibility & Plugin-Like Patterns

The “extraction/document” modules (e.g., driver_license.py, invoice.py) illustrate a flexible pattern for structured data extraction using Pydantic models. These modules serve as a blueprint for future expansions—such as bill_of_lading.py or evidence_photos.py—that can adopt the same approach. By modeling each document type with Pydantic, you gain:

- Strict data validation and consistent schemas per document type.
- A standardized structure for parsing and storing extracted fields, which simplifies maintenance and future enhancements.
- Reusability across multiple apps (Dispatch, Fleet, etc.) that require extracting structured data from various document types.

---

## 2. Quick Start Guides

### Local Development
- Clone the repo and copy `.env.example` to `.env`, setting up the DB, Redis, Celery, and AWS/OpenAI keys.
- Run `docker compose --profile dev up -d` (or `make dev-up`) to launch the environment.
- Populate the DB with initial data:
  - `docker compose exec web python manage.py migrate`
  - Optionally, run `createsuperuser`.

### Creating a New Tenant
- Sign in with the superuser.
- Navigate to **Tenant Management** → **Onboard Organization**. Enter tenant details, then add one or more users.
- Verify your new Tenant is created and visible in the admin.

### Creating a New Order
- Under **Dispatch**, click **Create Order**.
- Upload a PDF document (e.g., invoice or BOL).
- The system checks your `monthly_order_limit` to ensure the usage is within quota.

---

## 3. Common Workflows

### New User Onboarding
- Tenant admin logs in and navigates to **Add New User**.
- Fills out user information; this action triggers the creation of a new Profile.
- Optionally grants user roles (staff, read-only, etc.).

### Posting a New Dispatch
- Create an order first.
- Create a trip or dispatch referencing carriers from Fleet.
- Celery tasks may run (optionally) to generate shipping labels or parse documents.

### Managing Quotas
- Access usage logs from the Subscriptions dashboard.
- Quota alerts will appear if thresholds are reached (e.g., “80% monthly usage”).
- Update subscription levels to increase usage limits if needed.

---

## 4. Best Practices for Debugging & Testing

### Debugging
- Use Django's `DEBUG=True` in `.env` for local development.
- `django-debug-toolbar` is installed to help profile queries.
- Check logs in `/var/log/django.log` inside the container or run `docker compose logs -f web`.

### Testing
- Write unit tests for each view (e.g., `test_order_create`) to ensure correct usage logging.
- Use integration tests to verify end-to-end flows (e.g., tenant creation → new user → order upload → usage log).
- Run `pytest --cov=.` or `python manage.py test` for coverage.

### Performance Optimization
- Verify database indexes for frequently queried fields (e.g., `tenant_id`).
- Look out for N+1 query patterns in Celery tasks that loop over model relationships.
- Cache frequently accessed, yet static, data (like pricing tiers and subscription checks) when needed.

---

## 5. Additional Tips & Guidelines

### API & Model Documentation
- Use docstrings for every function in `views/`, `utils/`, and `models/`.
- Keep the documentation updated as business rules evolve.

### Version Control & Branching
- Use feature branches for new modules or changes to existing code.
- Merge into the main branch only after passing tests and code reviews.

### Continuous Integration / Deployment
- Automate Docker build and test steps using CI tools (e.g., GitHub Actions).
- Use environment-based deployment pipelines for staging versus production.

---

By following these guidelines, new developers can quickly get up to speed on the various services in this multi-tenant environment, efficiently manage advanced workflows for order/dispatch management, and ensure subscription-based usage limits are respected.
