from django import template

register = template.Library()


@register.filter(name="addClass")
def addClass(value, arg):
    return value.as_widget(attrs={"class": arg})


@register.filter(name="sub")
def sub(value, arg):
    """Subtracts the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ""
