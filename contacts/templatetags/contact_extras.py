# templatetags/contact_extras.py

from django import template

register = template.Library()


@register.filter
def highlight(value, query):
    """
    I use this filter to highlight search matches in UI.
    """
    if query:
        return value.replace(query, f"<mark>{query}</mark>")
    return value