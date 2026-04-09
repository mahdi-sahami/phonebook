"""
I keep small presentation helpers here so my templates stay expressive without
becoming cluttered with repetitive formatting logic.
"""

from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.filter
def contact_initials(value: str) -> str:
    """
    I convert a full name into initials for use in avatar circles.
    """
    parts: list[str] = [part for part in value.split() if part]
    if not parts:
        return "NA"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


@register.simple_tag
def active_class(request: Any, url_name: str) -> str:
    """
    I return a CSS class when the current route matches the given url name.
    """
    match = getattr(request, "resolver_match", None)
    if match and match.url_name == url_name:
        return "is-active"
    return ""


@register.filter
def filled_count(contact: dict[str, Any]) -> int:
    """
    I count how many visible fields are filled so I can display simple UI
    completeness badges.
    """
    fields: tuple[str, ...] = ("name", "phone", "email", "address")
    return sum(1 for field in fields if str(contact.get(field, "")).strip())