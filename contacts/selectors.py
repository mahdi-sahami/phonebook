"""
I keep frontend-oriented filtering, searching, and sorting logic here so my
views remain thin and easier to test.
"""

from __future__ import annotations

from typing import Any


def apply_contact_filters(contacts: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    """
    I apply search and advanced filters to the contact collection already
    returned by my API.
    """
    q: str = (filters.get("q") or "").strip().lower()
    email: str = (filters.get("email") or "").strip().lower()
    address: str = (filters.get("address") or "").strip().lower()
    ordering: str = (filters.get("ordering") or "name").strip()

    filtered: list[dict[str, Any]] = contacts

    if q:
        filtered = [
            contact
            for contact in filtered
            if q in str(contact.get("name", "")).lower()
            or q in str(contact.get("phone", "")).lower()
            or q in str(contact.get("email", "")).lower()
            or q in str(contact.get("address", "")).lower()
        ]

    if email:
        filtered = [
            contact for contact in filtered if email in str(contact.get("email", "")).lower()
        ]

    if address:
        filtered = [
            contact for contact in filtered if address in str(contact.get("address", "")).lower()
        ]

    reverse: bool = ordering.startswith("-")
    field_name: str = ordering.lstrip("-")

    filtered.sort(key=lambda item: str(item.get(field_name, "")).lower(), reverse=reverse)
    return filtered


def build_suggestions(contacts: list[dict[str, Any]], query: str, limit: int = 6) -> list[str]:
    """
    I generate live-search suggestions from name, phone, and email fields so
    the UI feels fast and helpful.
    """
    normalized_query: str = query.strip().lower()
    if not normalized_query:
        return []

    suggestions: list[str] = []
    seen: set[str] = set()

    for contact in contacts:
        for candidate in (
            str(contact.get("name", "")).strip(),
            str(contact.get("phone", "")).strip(),
            str(contact.get("email", "")).strip(),
        ):
            if candidate and normalized_query in candidate.lower() and candidate.lower() not in seen:
                suggestions.append(candidate)
                seen.add(candidate.lower())

    return suggestions[:limit]