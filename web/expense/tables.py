import django_tables2 as tables # type: ignore
from django.utils.html import format_html
from expense.models import BVD


class BVDTable(tables.Table):
    driver = tables.Column(accessor='driver.get_full_name', verbose_name="Driver")
    actions = tables.Column(empty_values=(), orderable=False)

    class Meta:
        model = BVD
        template_name = "django_tables2/bootstrap5.html"
        attrs = {
            "class": "table table-striped table-hover",
            "thead": {"class": "table-light"},
        }
        fields = [
            "date",
            "unit",
            "driver",
            "site_name",
            "quantity",
            "amount",
        ]

    def render_date(self, value):
        return value.strftime("%Y-%m-%d %H:%M")

    def render_quantity(self, value, record):
        return f"{value:.2f} {record.uom}"

    def render_amount(self, value, record):
        return f"{value:.2f} {record.currency}"

    def render_site_name(self, value, record):
        return f"{value}, {record.site_city}"

    def render_actions(self, record):
        return format_html(
            '<a href="{}" class="btn btn-sm btn-info">View</a> '
            '<a href="{}" class="btn btn-sm btn-warning">Edit</a> '
            '<form action="{}" method="post" class="d-inline">'
            '    <input type="hidden" name="csrfmiddlewaretoken" value="">'
            '    <button type="submit" class="btn btn-sm btn-danger" '
            "            onclick=\"return confirm('Are you sure?')\">Delete</button>"
            "</form>",
            f"/fuel-expenses/bvd/{record.pk}/",
            f"/fuel-expenses/bvd/{record.pk}/update/",
            f"/fuel-expenses/bvd/{record.pk}/delete/",
        )


class ExpenseTable(tables.Table):
    edit = tables.Column(empty_values=(), orderable=False)
    delete = tables.Column(empty_values=(), orderable=False)
    amount_display = tables.Column(empty_values=(), verbose_name="Amount")

    class Meta:
        model = Expense
        template_name = "django_tables2/bootstrap5.html"
        fields = ["date", "name", "amount_display", "status", "driver", "truck"]
        attrs = {"class": "table table-hover"}
        row_attrs = {"data-href": lambda record: record.pk}

    def render_edit(self, record):
        return format_html(
            '<a href="{}" class="btn btn-sm btn-primary">Edit</a>',
            f"/expenses/{record.pk}/edit/",
        )

    def render_delete(self, record):
        return format_html(
            '<button type="button" class="btn btn-sm btn-danger" '
            'onclick="deleteExpense({})">Delete</button>',
            record.pk,
        )

    def render_amount_display(self, record):
        if record.amount and record.currency:
            return f"{record.amount:,.2f} {record.currency}"
        return "-"

    def render_date(self, value):
        return value.strftime("%Y-%m-%d %H:%M")
