# Project Configuration, Environment, and Deployment Overview

Below is an overview of how this project handles configuration, environment management, and deployment based on the provided code excerpts. It highlights key points in `settings.py`, Docker/Makefile usage, `.env` handling, and dependency management via `pyproject.toml`.

---

## 1. Settings and Configuration (`settings.py`)

### Environment Variables via python-decouple
- **Usage:**
  - The project imports `config` from decouple at the top of `settings.py`.
  - Core settings such as `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, AWS credentials, etc. are read from environment variables.
- **Benefits:**
  - Sensitive information (database credentials, AWS keys, Django secret key, etc.) remains outside source control.

### Installed Apps
- **Components:**
  - Django’s built-in apps and third-party libraries (e.g., `django_tables2`, `django_celery_results`, `debug_toolbar`, etc.).
  - Custom “Local apps” include:
    - `customer`
    - `models`
    - `tenant`
    - `subscriptions`
    - `dispatch`
    - `fleet`
    - `expense`

### Middleware
- **Key Middleware:**
  - `debug_toolbar.middleware.DebugToolbarMiddleware` for development debugging.
  - `whitenoise.middleware.WhiteNoiseMiddleware` for static file serving.
  - A custom middleware: `tenant.middleware.StorageQuotaMiddleware`.

### Database Configuration
- **Configuration Switching:**
  - Uses `DB_MODE` from `.env` to determine the database backend.
  - Defaults to SQLite if `DB_MODE=sqlite`; otherwise, uses PostgreSQL (`ENGINE=django.db.backends.postgresql`).
- **Additional Settings:**
  - `HOST`, `PORT`, `USER`, and `PASSWORD` are loaded from environment variables.

### Static and Media Files
- **Static Files:**
  - `STATIC_URL = "static/"` with a `STATIC_ROOT` pointing to `tmp/staticfiles`.
  - WhiteNoise is configured to serve static assets in production.
- **Media Files:**
  - `MEDIA_URL` and `MEDIA_ROOT` are set up for user-uploaded files.

### Logging
- **Log Handlers:**
  - Two `RotatingFileHandlers`:
    - General logs (`django.log`)
    - Error logs (`error.log`)
- **Logging Configuration:**
  - The `django` logger is set to `INFO` level.
  - Errors get routed to `error.log` with `ERROR` level.

### Celery Configuration
- **Broker and Scheduler:**
  - `CELERY_BROKER_URL` is obtained from `.env` (default: `redis://localhost:6379/0`).
  - `CELERY_BEAT_SCHEDULE` includes tasks such as `tenant.tasks.cleanup_incomplete_onboarding` and others.

---

## 2. Docker & Environment (`.env`, Docker Compose, Makefile)

### .env.example
- **Purpose:**
  - Serves as a blueprint for environment variables needed in the project.
- **Key Variables:**
  - `DEBUG`
  - `SECRET_KEY`
  - `DATABASE_URL`
  - AWS credentials
  - OpenAI key, etc.
- **Note:**
  - The actual `.env` file (which is uncommitted) contains the real secrets.

### Makefile
- **Developer Commands:**
  - Provides short commands for common tasks (`runserver`, `migrate`, `createsuperuser`), prefixed with `uv run ...` to execute inside containers.
- **Profiles:**
  - Differentiates between **dev** (local development) and **prod** (production builds) using Docker Compose profiles.
- **Targets:**
  - Includes targets for `collectstatic`, migration, image building, log checking, and container management.

### Docker Compose
- **Setup:**
  - Likely implemented using one or more `docker-compose.yml` files that cater to different profiles (e.g., `dev`, `prod`, `only-dbs`).
- **Usage:**
  - Makefile commands reference Docker Compose using commands like `docker compose --profile <profile> ...`.

---

## 3. Dependency Management (`pyproject.toml`)

- **Tooling:**
  - The project uses `pyproject.toml` for managing dependencies via a tool like Poetry, Hatch, or a similar system.
- **Project Dependencies:**
  - The `[project]` section specifies pinned versions for:
    - Django (e.g., `django>=5.1.2`)
    - Celery (>=5.4.0)
    - django-tables2 (>=2.7.0)
    - psycopg2-binary (>=2.9.10)
    - And other libraries for PDF manipulation, date formatting, AWS (`boto3>=1.35.57`), Plotly, and more.
- **Development Dependencies:**
  - Listed under `[tool.uv]` and include tools like:
    - Bandit (security checks)
    - MkDocs (documentation)
  - This structured approach enhances security, documentation, and local development.

---

## 4. Putting It All Together

### Local vs. Production
- **Configuration Toggle:**
  - The `DEBUG` flag (loaded from `config("DEBUG")`) switches between local and production settings.
- **Production Readiness:**
  - When `DEBUG=False`, settings such as `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` enforce stricter, production-level behavior.

### Secret & Sensitive Data
- **Handling:**
  - Secrets and database configurations are loaded at runtime from environment variables, ensuring they remain out of version control.

### Static & Media Handling
- **Static Files:**
  - WhiteNoise is used in production to optimize static file serving.
- **Build Process:**
  - The Makefile’s `collectstatic` target assembles all static files into `STATIC_ROOT`, which are then served by WhiteNoise or accessed via the container.

### Docker Workflow
- **Environment Consistency:**
  - Docker Compose is used to spin up containers for the application, database, and Redis seamlessly across both development and production.
- **Makefile Utility:**
  - Commands for migrations, static file collection, etc., are executed within the defined containers, ensuring consistent behavior.

### Deployment Steps (Typical Example)
1. **Build Containers:**
   ```bash
   docker compose --profile prod build
   ```
2. Run Migrations:
    ```bash
    docker compose --profile prod exec -it web uv run python manage.py migrate
    ```
3. Collect Static Files:
    ```bash
    docker compose --profile prod exec -it web uv run python manage.py collectstatic
    ```
4. Start Containers:
    ```bash
    docker compose --profile prod up -d
    ```
5. Overall, the project is well-organized for container-based deployment. Environment variables facilitate dynamic configuration for both local and production environments, and pinned dependencies in pyproject.toml ensure consistent package versions across environments.