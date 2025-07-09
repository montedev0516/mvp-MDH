import django_tables2 as tables  # type: ignore
from django.urls import reverse  # type: ignore
from django.utils.html import format_html  # type: ignore
from dispatch.models import Order


class OrderTable(tables.Table):
    """Table for displaying orders in a paginated format."""

    created_at = tables.DateTimeColumn(
        format="M d, Y, P",
        verbose_name="Created On",
        attrs={"td": {"class": "text-nowrap"}}
    )
    
    pickup_date = tables.DateTimeColumn(
        format="M d, Y",
        verbose_name="Pickup Date",
        attrs={"td": {"class": "text-nowrap"}}
    )
    
    delivery_date = tables.DateTimeColumn(
        format="M d, Y",
        verbose_name="Delivery Date",
        attrs={"td": {"class": "text-nowrap"}}
    )
    
    status = tables.Column(
        verbose_name="Status",
        attrs={"td": {"class": "text-center"}}
    )
    
    load_total = tables.Column(
        verbose_name="Load Total",
        attrs={"td": {"class": "text-end"}}
    )
    
    actions = tables.TemplateColumn(
        template_code="""
        <div class="btn-group">
            <a href="{% url 'dispatch:order_detail' pk=record.pk %}" 
               class="btn btn-sm btn-info" title="View Order">
                <i class="fas fa-eye"></i>
            </a>
            <a href="{% url 'dispatch:order_edit' pk=record.pk %}" 
               class="btn btn-sm btn-warning" title="Edit Order">
                <i class="fas fa-edit"></i>
            </a>
            <button type="button" 
                    class="btn btn-sm btn-danger" 
                    data-bs-toggle="modal" 
                    data-bs-target="#deleteModal{{ record.pk }}"
                    title="Delete Order">
                <i class="fas fa-trash"></i>
            </button>
        </div>
        """,
        verbose_name="Actions",
        orderable=False
    )

    class Meta:
        model = Order
        template_name = "django_tables2/bootstrap5.html"
        fields = (
            "order_number",
            "customer_name",
            "origin",
            "destination",
            "cargo_type",
            "pickup_date",
            "delivery_date",
            "status",
            "load_total",
            "load_currency",
            "created_at",
            "actions",
        )
        attrs = {
            "class": "table table-bordered table-striped table-hover align-middle",
            "thead": {"class": "table-primary"},
        }
        order_by = ("-created_at",)
        empty_text = "No orders available."

    def render_order_number(self, value):
        """Render order number with a copy button."""
        return format_html(
            '<div class="d-flex align-items-center">'
            '<span>{}</span>'
            '<button class="btn btn-sm btn-link ms-2 copy-btn" '
            'data-clipboard-text="{}" title="Copy Order Number">'
            '<i class="fas fa-copy"></i>'
            '</button>'
            '</div>',
            value,
            value
        )

    def render_customer_name(self, value):
        """Render customer name with ellipsis if too long."""
        if value:
            short_name = value[:30]
            return format_html(
                '<span title="{}">{}{}</span>',
                value,
                short_name,
                "..." if len(value) > 30 else ""
            )
        return "-"

    def render_origin(self, value):
        """Render origin address with tooltip."""
        if value:
            short_address = value[:20]
            return format_html(
                '<span title="{}" class="text-truncate d-inline-block" '
                'style="max-width: 200px;">{}{}</span>',
                value,
                short_address,
                "..." if len(value) > 20 else ""
            )
        return "-"

    def render_destination(self, value):
        """Render destination address with tooltip."""
        if value:
            short_address = value[:20]
            return format_html(
                '<span title="{}" class="text-truncate d-inline-block" '
                'style="max-width: 200px;">{}{}</span>',
                value,
                short_address,
                "..." if len(value) > 20 else ""
            )
        return "-"

    def render_status(self, value, record):
        """Render status with appropriate color badge."""
        status_colors = {
            'PENDING': 'secondary',
            'IN_PROGRESS': 'primary',
            'COMPLETED': 'success',
            'CANCELLED': 'danger',
            'ASSIGNED': 'info',
            'IN_TRANSIT': 'warning',
            'DELIVERED': 'success',
            'INVOICED': 'dark',
            'PAYMENT_RECEIVED': 'success'
        }
        color = status_colors.get(value, 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            record.get_status_display()
        )

    def render_load_total(self, value, record):
        """Render load total with currency."""
        if value is not None:
            currency = record.load_currency or ''
            try:
                formatted_value = "{:.2f}".format(float(value))
                return format_html(
                    '<span class="fw-bold">{} {}</span>',
                    currency,
                    formatted_value
                )
            except (ValueError, TypeError):
                return str(value)
        return "-"
