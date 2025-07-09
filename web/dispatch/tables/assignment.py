import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from dispatch.models import DriverTruckAssignment


class AssignmentTable(tables.Table):
    """Table for displaying driver-truck assignments in a paginated format."""

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

    start_date = tables.DateTimeColumn(
        format="M d, Y",
        verbose_name="Start Date",
        attrs={"td": {"class": "text-nowrap"}}
    )

    end_date = tables.DateTimeColumn(
        format="M d, Y",
        verbose_name="End Date",
        attrs={"td": {"class": "text-nowrap"}}
    )

    status = tables.Column(
        verbose_name="Status",
        attrs={"td": {"class": "text-center"}}
    )

    odometer_readings = tables.Column(
        empty_values=(),
        verbose_name="Odometer",
        orderable=False,
        attrs={"td": {"class": "small"}}
    )

    actions = tables.TemplateColumn(
        template_code="""
        <div class="btn-group">
            <a href="{% url 'dispatch:assignment_detail' pk=record.pk %}" 
               class="btn btn-sm btn-info" title="View Assignment">
                <i class="fas fa-eye"></i>
            </a>
            {% if record.status not in 'OFF_DUTY,CANCELLED' %}
            <a href="{% url 'dispatch:assignment_edit' pk=record.pk %}" 
               class="btn btn-sm btn-warning" title="Edit Assignment">
                <i class="fas fa-edit"></i>
            </a>
            <button type="button" 
                    class="btn btn-sm btn-danger" 
                    data-bs-toggle="modal" 
                    data-bs-target="#deleteModal{{ record.pk }}"
                    title="Delete Assignment">
                <i class="fas fa-trash"></i>
            </button>
            {% endif %}
        </div>
        """,
        verbose_name="Actions",
        orderable=False
    )

    class Meta:
        model = DriverTruckAssignment
        template_name = "django_tables2/bootstrap5.html"
        fields = (
            "driver",
            "truck",
            "start_date",
            "end_date",
            "status",
            "odometer_readings",
            "actions",
        )
        attrs = {
            "class": "table table-bordered table-striped table-hover align-middle",
            "thead": {"class": "table-primary"},
        }
        empty_text = "No assignments available."
        order_by = ("-start_date",)

    def render_driver(self, value):
        """Render driver name with icon and carrier info."""
        if not value:
            return "-"
        carrier_name = value.carrier.name if value.carrier else "No Carrier"
        return format_html(
            '<div class="d-flex flex-column gap-1">'
            '<div><i class="fas fa-user text-primary"></i> {} {}</div>'
            '<div class="small text-muted"><i class="fas fa-building"></i> {}</div>'
            '</div>',
            value.first_name,
            value.last_name,
            carrier_name
        )

    def render_truck(self, value):
        """Render truck info with icon and details."""
        if not value:
            return "-"
        return format_html(
            '<div class="d-flex flex-column gap-1">'
            '<div><i class="fas fa-truck text-secondary"></i> #{}</div>'
            '<div class="small text-muted">{}</div>'
            '</div>',
            value.unit,
            value.plate
        )

    def render_status(self, value, record):
        """Render status with appropriate color badge."""
        status_colors = {
            "unassigned": "secondary",
            "assigned": "primary",
            "on_duty": "success",
            "off_duty": "warning",
            "cancelled": "danger",
        }
        color = status_colors.get(value.lower(), "secondary")
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color,
            record.get_status_display()
        )

    def render_odometer_readings(self, record):
        """Render odometer readings with start and end values."""
        start = record.odometer_start or 0
        end = record.odometer_end or "-"
        
        if end != "-":
            distance = end - start
            return format_html(
                '<div class="d-flex flex-column gap-1">'
                '<div><i class="fas fa-play text-success"></i> {:,}</div>'
                '<div><i class="fas fa-stop text-danger"></i> {:,}</div>'
                '<div class="small text-muted">Distance: {:,} km</div>'
                '</div>',
                start,
                end,
                distance
            )
        
        return format_html(
            '<div class="d-flex flex-column gap-1">'
            '<div><i class="fas fa-play text-success"></i> {:,}</div>'
            '<div><i class="fas fa-stop text-danger"></i> {}</div>'
            '</div>',
            start,
            end
        ) 