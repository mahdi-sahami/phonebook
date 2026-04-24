"""
I keep frontend-oriented filtering, searching, and sorting logic here so my
views remain thin and easier to test.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from .models import Contact
from django.db.models import Q

def apply_contact_filters(filters: dict[str, str], user: User) -> list[dict[str, Any]]:
    """
    I apply search and advanced filters to the contact collection already
    returned by my API.
    """
    q: str = (filters.get("q") or "").strip().lower()
    email: str = (filters.get("email") or "").strip().lower()
    address: str = (filters.get("address") or "").strip().lower()
    ordering: str = (filters.get("ordering") or "name").strip()

    q_name = Q(name__icontains=q) if q else Q()
    q_phone = Q(phone__icontains=q) if q else Q()
    q_address = Q(address__icontains=address) if address else Q()
    q_email = Q(email__icontains=email) if email else Q()
    q_owner = Q(owner=user)

    result = Contact.objects.filter(
        q_owner & (
            q_name | q_phone | q_email | q_address
        )
    ).order_by(ordering)
    
    return list(result.values())
    


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