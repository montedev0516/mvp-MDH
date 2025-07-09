import django_tables2 as tables
from django.contrib.auth.models import User
from django.utils.html import format_html


class UserTable(tables.Table):
    tenant = tables.Column(accessor="profile.tenant.name", verbose_name="Tenant")
    full_name = tables.Column(
        accessor="get_full_name", verbose_name="Full Name", orderable=False
    )
    role = tables.Column(accessor="profile.role", verbose_name="Role")
    status = tables.Column(empty_values=())
    actions = tables.TemplateColumn(
        template_code="""
            <a href="{% url 'tenant:user_edit' record.id %}" class="btn btn-sm btn-primary">
                <i class="bi bi-pencil"></i> Edit
            </a>
            <button class="btn btn-sm btn-danger delete-user" data-id="{{ record.id }}">
                <i class="bi bi-trash"></i> Delete
            </button>
        """,
        verbose_name="Actions",
        orderable=False,
    )

    class Meta:
        model = User
        template_name = "django_tables2/bootstrap5.html"
        fields = ("username", "email", "full_name", "tenant", "role", "status")
        attrs = {"class": "table table-striped table-hover"}

    def render_status(self, record):
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            "success" if record.is_active else "danger",
            "Active" if record.is_active else "Inactive",
        )
