"""
LangChain tools that bridge the AI agent to the contact service layer.

Design principles applied here:
- **SRP**: each tool has one job (create / update / delete / search).
- **DRY**: all tools are built by a single factory ``build_tools``.
- **SOC**: tools know nothing about HTTP, sessions, or LangGraph state —
  they call service/selector functions and return plain strings.
- Every tool provides both a synchronous ``_run`` and an asynchronous
  ``_arun`` implementation so the agent can be invoked in either mode.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Type

from django.contrib.auth.models import User
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from contacts.selectors import apply_contact_filters
from contacts.services import build_contact_api_service

from .enums import ToolName


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic input schemas (one per tool)
# ─────────────────────────────────────────────────────────────────────────────


class CreateContactInput(BaseModel):
    """Input schema for the create-contact tool."""

    name: str = Field(..., description="Full name of the contact (required).")
    phone: str = Field(..., description="Phone number of the contact (required).")
    email: Optional[str] = Field(None, description="Email address (optional).")
    address: Optional[str] = Field(None, description="Street address (optional).")


class UpdateContactInput(BaseModel):
    """Input schema for the update-contact tool."""

    contact_id: int = Field(..., description="Numeric ID of the contact to update.")
    name: Optional[str] = Field(None, description="New name (optional).")
    phone: Optional[str] = Field(None, description="New phone number (optional).")
    email: Optional[str] = Field(None, description="New email address (optional).")
    address: Optional[str] = Field(None, description="New address (optional).")


class DeleteContactInput(BaseModel):
    """Input schema for the delete-contact tool."""

    contact_id: int = Field(..., description="Numeric ID of the contact to delete.")


class SearchContactsInput(BaseModel):
    """Input schema for the search-contacts tool."""

    q: Optional[str] = Field(
        None, description="Free-text query matched against name and phone."
    )
    email: Optional[str] = Field(None, description="Partial email filter.")
    address: Optional[str] = Field(None, description="Partial address filter.")
    ordering: Optional[str] = Field(
        "name",
        description=(
            "Sort field: 'name', '-name', 'phone', '-phone'. "
            "Prefix with '-' for descending order."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations (BaseTool subclasses)
# ─────────────────────────────────────────────────────────────────────────────


class CreateContactTool(BaseTool):
    """
    Create a new contact in the phonebook for the current user.

    Calls ``ContactApiService.create_contact`` directly via the ORM —
    no HTTP round-trips.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = ToolName.CREATE_CONTACT.value
    description: str = (
        "Create a new contact. "
        "Requires 'name' and 'phone'. 'email' and 'address' are optional."
    )
    args_schema: Type[BaseModel] = CreateContactInput

    # Injected at construction time; excluded from the LangChain schema.
    user: User = Field(exclude=True)

    def _run(
        self,
        name: str,
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> str:
        """
        Synchronous execution — delegates to the contact service layer.

        Returns a human-readable confirmation string for the LLM.
        """
        payload: dict[str, Any] = {"name": name, "phone": phone}
        if email:
            payload["email"] = email
        if address:
            payload["address"] = address

        service = build_contact_api_service()
        result = service.create_contact(self.user, payload)

        if result.ok:
            return (
                f"Contact '{result.data['name']}' created successfully "
                f"(ID: {result.data['id']}, phone: {result.data['phone']})."
            )
        return f"Failed to create contact: {result.error_message}"

    async def _arun(
        self,
        name: str,
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> str:
        """
        Asynchronous execution — wraps the synchronous ORM call in a
        thread-pool executor so it does not block the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run(name=name, phone=phone, email=email, address=address),
        )


class UpdateContactTool(BaseTool):
    """
    Update one or more fields of an existing contact owned by the current user.

    Calls ``ContactApiService.update_contact`` via the ORM.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = ToolName.UPDATE_CONTACT.value
    description: str = (
        "Update an existing contact by its numeric ID. "
        "Provide only the fields that should change."
    )
    args_schema: Type[BaseModel] = UpdateContactInput

    user: User = Field(exclude=True)

    def _run(
        self,
        contact_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> str:
        """Synchronous execution — delegates to the contact service layer."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if phone is not None:
            payload["phone"] = phone
        if email is not None:
            payload["email"] = email
        if address is not None:
            payload["address"] = address

        if not payload:
            return "No fields provided to update. Please specify at least one field."

        service = build_contact_api_service()
        result = service.update_contact(self.user, contact_id, payload)

        if result.ok:
            return (
                f"Contact ID {contact_id} updated successfully. "
                f"Current values — name: '{result.data['name']}', "
                f"phone: '{result.data['phone']}'."
            )
        return f"Failed to update contact: {result.error_message}"

    async def _arun(
        self,
        contact_id: int,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
    ) -> str:
        """Asynchronous execution — wraps the sync ORM call in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run(
                contact_id=contact_id,
                name=name,
                phone=phone,
                email=email,
                address=address,
            ),
        )


class DeleteContactTool(BaseTool):
    """
    Permanently delete a contact owned by the current user.

    Calls ``ContactApiService.delete_contact`` via the ORM.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = ToolName.DELETE_CONTACT.value
    description: str = (
        "Permanently delete a contact by its numeric ID. "
        "This action cannot be undone."
    )
    args_schema: Type[BaseModel] = DeleteContactInput

    user: User = Field(exclude=True)

    def _run(self, contact_id: int) -> str:
        """Synchronous execution — delegates to the contact service layer."""
        service = build_contact_api_service()
        result = service.delete_contact(self.user, contact_id)

        if result.ok:
            return f"Contact ID {contact_id} has been permanently deleted."
        return f"Failed to delete contact: {result.error_message}"

    async def _arun(self, contact_id: int) -> str:
        """Asynchronous execution — wraps the sync ORM call in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run(contact_id=contact_id),
        )


class SearchContactsTool(BaseTool):
    """
    Search and filter the current user's contacts.

    Delegates to ``apply_contact_filters`` from the selectors layer,
    keeping query logic DRY and consistent with the template frontend.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = ToolName.SEARCH_CONTACTS.value
    description: str = (
        "Search contacts by name/phone keyword, email, or address. "
        "Returns a formatted list of matching contacts with their IDs."
    )
    args_schema: Type[BaseModel] = SearchContactsInput

    user: User = Field(exclude=True)

    def _run(
        self,
        q: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        ordering: Optional[str] = "name",
    ) -> str:
        """Synchronous execution — delegates to the selector layer."""
        filters: dict[str, str] = {
            "q": q or "",
            "email": email or "",
            "address": address or "",
            "ordering": ordering or "name",
        }
        contacts: list[dict[str, Any]] = apply_contact_filters(filters, self.user)

        if not contacts:
            return "No contacts found matching your search criteria."

        lines: list[str] = [f"Found {len(contacts)} contact(s):"]
        for c in contacts:
            parts: list[str] = [
                f"  • ID {c['id']}: {c['name']} — {c['phone']}"
            ]
            if c.get("email"):
                parts.append(f"    email: {c['email']}")
            if c.get("address"):
                parts.append(f"    address: {c['address']}")
            lines.extend(parts)

        return "\n".join(lines)

    async def _arun(
        self,
        q: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        ordering: Optional[str] = "name",
    ) -> str:
        """Asynchronous execution — wraps the sync ORM call in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._run(q=q, email=email, address=address, ordering=ordering),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────


def build_tools(user: User) -> list[BaseTool]:
    """
    Instantiate all four contact-management tools bound to *user*.

    The user is injected here so the tools are always scoped to the
    currently authenticated person — no tool can accidentally touch
    another user's data.

    Args:
        user: The authenticated Django ``User`` whose contacts the
              agent is allowed to manage.

    Returns:
        A list of four ``BaseTool`` instances ready to be bound to the LLM.
    """
    return [
        CreateContactTool(user=user),
        UpdateContactTool(user=user),
        DeleteContactTool(user=user),
        SearchContactsTool(user=user),
    ]
