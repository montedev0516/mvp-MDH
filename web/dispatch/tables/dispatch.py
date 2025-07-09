import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from dispatch.models import Dispatch


class DispatchTable(tables.Table):
    """Table for displaying dispatches in a paginated format."""

    dispatch_id = tables.Column(
        accessor="dispatch_id",
        verbose_name="Dispatch ID",
        attrs={"td": {"class": "text-nowrap"}}
    )   

    order_number = tables.Column(
        accessor="order.order_number",
        verbose_name="Order Number",
        attrs={"td": {"class": "text-nowrap"}}
    )

    order_date = tables.DateColumn(
        accessor="order.created_at",
        format="M d, Y",
        verbose_name="Order Date",
        attrs={"td": {"class": "text-nowrap"}}
    )

    status = tables.Column(
        verbose_name="Status",
        attrs={"td": {"class": "text-center"}}
    )

    driver = tables.Column(
        accessor="driver",
        verbose_name="Driver",
        attrs={"td": {"class": "small"}}
    )

    truck = tables.Column(
        accessor="truck",
        verbose_name="Truck",
        attrs={"td": {"class": "small"}}
    )

    carrier = tables.Column(
        accessor="carrier",
        verbose_name="Carrier",
        attrs={"td": {"class": "small"}}
    )

    load_total = tables.Column(
        accessor="order.load_total",
        verbose_name="Load Total",
        attrs={"td": {"class": "text-end"}}
    )

    commission_amount = tables.Column(
        verbose_name="Commission",
        attrs={"td": {"class": "text-end"}}
    )

    actions = tables.TemplateColumn(
        template_code="""
        <div class="btn-group">
            <a href="{% url 'dispatch:dispatch_detail' pk=record.pk %}" 
               class="btn btn-sm btn-info" title="View Dispatch">
                <i class="fas fa-eye"></i>
            </a>
            <a href="{% url 'dispatch:dispatch_update' pk=record.pk %}" 
               class="btn btn-sm btn-warning" title="Edit Dispatch">
                <i class="fas fa-edit"></i>
            </a>
            <button type="button" 
                    class="btn btn-sm btn-danger delete-btn" 
                    data-dispatch-id="{{ record.pk }}"
                    title="Delete Dispatch">
                <i class="fas fa-trash"></i>
            </button>
        </div>
        """,
        verbose_name="Actions",
        orderable=False
    )

    class Meta:
        model = Dispatch
        template_name = "django_tables2/bootstrap5.html"
        sequence = (
            "dispatch_id",
            "order_number",
            "order_date",
            "status",
            "driver",
            "truck",
            "carrier",
            "load_total",
            "commission_amount",
            "actions",
        )
        exclude = (
            "id",
            "updated_at",
            "is_active",
            "order",
            "customer",
            "commission_percentage",
            "commission_currency",
            "deleted_at",
            "tenant",
            "notes",
            "trip",
            "created_at"
        )
        attrs = {
            "class": "table table-bordered table-striped table-hover align-middle",
            "thead": {"class": "table-primary"},
        }
        empty_text = "No dispatches available."
        order_by = ("-created_at",)

    def render_order_number(self, value):
        """Render order number with copy button."""
        if not value:
            return "-"
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

    def render_driver(self, value):
        """Render driver name with icon."""
        if not value:
            return "-"
        return format_html(
            '<div class="d-flex align-items-center">'
            '<i class="fas fa-user text-primary me-2"></i>'
            '{} {}'
            '</div>',
            value.first_name,
            value.last_name
        )

    def render_truck(self, value):
        """Render truck info with icon."""
        if not value:
            return "-"
        return format_html(
            '<div class="d-flex align-items-center">'
            '<i class="fas fa-truck text-secondary me-2"></i>'
            '#{} {}'
            '</div>',
            value.unit,
            value.plate
        )

    def render_carrier(self, value):
        """Render carrier name with icon."""
        if not value:
            return "-"
        return format_html(
            '<div class="d-flex align-items-center">'
            '<i class="fas fa-building text-info me-2"></i>'
            '{}'
            '</div>',
            value.name
        )

    def render_load_total(self, value):
        """Render load total with currency."""
        if value is None or value == "":
            return "-"
        try:
            return format_html(
                '<span class="fw-bold">${:,.2f}</span>',
                float(value)
            )
        except (ValueError, TypeError):
            return str(value)

    def render_commission_amount(self, value):
        """Render commission amount with currency."""
        if value is None or value == "":
            return "-"
        try:
            return format_html(
                '<span class="fw-bold text-success">${:,.2f}</span>',
                float(value)
            )
        except (ValueError, TypeError):
            return str(value)

    def render_status(self, value, record):
        """Render status with appropriate color badge."""
        status_colors = {
            'pending': 'secondary',
            'assigned': 'primary',
            'in_transit': 'info',
            'delivered': 'success',
            'invoiced': 'warning',
            'payment_received': 'success',
            'completed': 'dark',
            'cancelled': 'danger'
        }
        color = status_colors.get(value.lower(), 'secondary')
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            record.get_status_display()
        )
