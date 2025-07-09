# Project-Wide Auditing/Logging Layer

Below are some ideas and practical steps for introducing or expanding a project-wide auditing/logging layer beyond the existing usage logs—especially relevant for critical actions like deleting a user, changing a subscription, or performing multi-tenant operations.

---

## 1. Decide Where to Store Audits

### Dedicated Model for Audits

Create (or extend) an `AuditLog` or `ActivityLog` model that captures events, who performed them, and relevant context. This model might look similar to `UsageLog` but store more general-purpose events. For example:

```python
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

class AuditLog(models.Model):
    action = models.CharField(max_length=50)  # e.g. "USER_DELETE", "SUBSCRIPTION_CHANGE"
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.CharField(max_length=36, blank=True)
    description = models.TextField(blank=True)  # freeform field for extra info

    def __str__(self):
        return f"{self.action} by {self.user} at {self.timestamp}"
```

### Expand Existing Usage Logs

If you prefer a single place for all activity, you could add more fields or actions to `UsageLog` and unify usage vs. general audits. However, if you want a clearer separation between “subscription/usage” concerns and general “audits,” it may be best to create a separate model.

---

## 2. Attach to Signals or Key Code Paths

### Model Signals

For important models (User, TenantSubscription, etc.), use Django signals (`post_save`, `post_delete`) to record changes in your new `AuditLog`.  
Example for user deletion:

```python
@receiver(post_delete, sender=User)
def user_deletion_audit(sender, instance, **kwargs):
    AuditLog.objects.create(
        action="USER_DELETE",
        description=f"Deleted user {instance.username}",
    )
```

### View or Service-Layer Hooks

Sometimes, you need more context than a signal can provide. For instance, changing a subscription might be done through a custom view or service. In that code path, you can explicitly create an entry in `AuditLog`:

```python
def update_subscription(...):
    # subscription update logic
    AuditLog.objects.create(
        action="SUBSCRIPTION_UPDATE",
        user=request.user,
        content_type=ContentType.objects.get_for_model(tenant_subscription),
        object_id=str(tenant_subscription.id),
        description=f"Changed subscription plan to {new_plan} for tenant {tenant_subscription.tenant.name}"
    )
```

### Admin/Command-Line Audits

Even if subscriptions are altered via custom management commands or an admin action, you can add an explicit `AuditLog` entry in that code.

---

## 3. Incorporate Tenant Context

Since the project is multi-tenant, always record the tenant if applicable. You can do this in a few ways:

- Add a tenant `ForeignKey` to your `AuditLog` model.
- Store the tenant’s ID in the `description` or `object_id` if a direct `ForeignKey` is not feasible.
- If usage logs are always associated with a `usage_period` (which has a tenant), you might store a direct reference to that same tenant.

---

## 4. Ensure Maintainability & Scalability

### Pruning or Archiving Old Logs

Auditing tables can become huge. You might want a scheduled Celery task to archive or purge old `AuditLog` entries or move them to an S3 bucket for longer retention.

### Indexing & Query Optimization

If you plan to query `AuditLog` frequently (e.g., by user or tenant), add appropriate indexes on tenant_id, user_id, or timestamp fields.

### Security Considerations

Audit logs often contain sensitive information. Make sure user permissions guard who can read these logs. In addition, consider anonymizing or hashing data that does not need to remain in plaintext.

---

## 5. Potential Tools & Approaches

- **django-simple-history or django-reversion**  
  These community packages track historical changes on models automatically. If you want full “diffs” (old vs. new field values), they can save effort—though they add overhead and complexity.

- **Code Audits in a “Core” Audit Layer**  
  If your project uses service classes (like `QuotaService`) or “manager” methods for critical actions, you can gather audits there. This ensures that any code path that triggers an operation also triggers an audit entry.

---

## 6. Putting It All Together

Below is a simplified example hooking a user-deletion audit and subscription changes in dedicated places:

- **Create an AuditLog model** with references to user, content type, object ID, tenant, and a freeform description.

- **In `signals.py`:**

```python
@receiver(post_delete, sender=User)
def user_deletion_audit(sender, instance, **kwargs):
    AuditLog.objects.create(
        action="USER_DELETE",
        description=f"Deleted user {instance.username}",
    )
```

- **In `views.py` or your subscription update logic:**

```python
def update_subscription(...):
    # subscription update logic
    AuditLog.objects.create(
        action="SUBSCRIPTION_UPDATE",
        user=request.user,
        content_type=ContentType.objects.get_for_model(tenant_subscription),
        object_id=str(tenant_subscription.id),
        description=f"Changed subscription plan to {new_plan} for tenant {tenant_subscription.tenant.name}"
    )
```

(Optional) Provide one or more admin views or Django Admin patterns to filter and display `AuditLog` entries by tenant, user, or date.

---

By combining these suggestions—dedicated `AuditLog` models, signals for model changes, explicit logging in key service/view layers, and a robust data-retention strategy—you can capture a high-level audit trail across the entire codebase. This not only helps debug multi-tenant operations (e.g., “Who changed that subscription?”) but also improves compliance and accountability for critical actions.