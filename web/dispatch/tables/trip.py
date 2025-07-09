import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from dispatch.models import Trip


class TripTable(tables.Table):
    """Table for displaying trips in a paginated format."""

    # Add action buttons
    actions = tables.TemplateColumn(
        template_name="partials/trip_actions.html",
        orderable=False,
        attrs={"class": "text-end"}
    )

    # Format created_at date
    created_at = tables.DateTimeColumn(
        format="Y-m-d H:i",
        attrs={"class": "text-nowrap"}
    )

    # Format status with badge
    status = tables.TemplateColumn(
        template_name="partials/status_badge.html",
        attrs={"class": "text-center"}
    )

    # Format origin/destination
    origin_destination = tables.Column(
        empty_values=(),
        orderable=False,
        attrs={"class": "text-wrap"}
    )

    # Format estimated distance
    estimated_distance = tables.Column(
        attrs={"class": "text-end"}
    )

    # Format freight value
    freight_value = tables.Column(
        attrs={"class": "text-end"}
    )

    def render_origin_destination(self, record):
        """Render origin and destination information."""
        if not record.order:
            return format_html(
                '<span class="text-muted">No order assigned</span>'
            )

        origin = record.order.origin or "Unknown Origin"
        destination = record.order.destination or "Unknown Destination"

        return format_html(
            '<div class="d-flex flex-column">'
            '<div class="mb-1">'
            '<i class="fas fa-map-marker-alt text-danger me-1"></i>'
            '<span class="text-truncate">{}</span>'
            '</div>'
            '<div>'
            '<i class="fas fa-map-marker-alt text-success me-1"></i>'
            '<span class="text-truncate">{}</span>'
            '</div>'
            '</div>',
            origin,
            destination
        )

    def render_estimated_distance(self, value):
        """Render estimated distance with unit."""
        if value is None:
            return format_html(
                '<span class="text-muted">N/A</span>'
            )
        formatted_value = "{:,.2f}".format(float(value))
        return format_html(
            '<span class="text-nowrap">{} km</span>',
            formatted_value
        )

    def render_freight_value(self, value, record):
        """Render freight value with currency."""
        if value is None:
            return format_html(
                '<span class="text-muted">N/A</span>'
            )
        formatted_value = "{:,.2f}".format(float(value))
        return format_html(
            '<span class="text-nowrap fw-bold">{} {}</span>',
            record.currency,
            formatted_value
        )

    class Meta:
        model = Trip
        template_name = "django_tables2/bootstrap5.html"
        fields = (
            "created_at",
            "origin_destination",
            "estimated_distance",
            "status",
            "freight_value",
            "actions"
        )
        attrs = {
            "class": "table table-striped table-hover align-middle",
            "thead": {
                "class": "table-light"
            }
        }
