"""
Enumeration constants for the AI agent module.

Using enums avoids magic strings scattered across the codebase (DRY)
and makes refactoring safe (a rename updates every reference).
"""

from __future__ import annotations

from enum import Enum


class ToolName(str, Enum):
    """
    Canonical identifiers for every LangChain tool exposed to the LLM.

    Inheriting from ``str`` lets the value be used directly wherever a
    plain string is expected (e.g. LangChain's ``name`` field) without
    an explicit ``.value`` call.
    """

    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    DELETE_CONTACT = "delete_contact"
    SEARCH_CONTACTS = "search_contacts"


class AgentNode(str, Enum):
    """
    Names of every node in the LangGraph state machine.

    Keeping these as an enum prevents typos when wiring graph edges.
    """

    RETRIEVE = "retrieve"
    AGENT = "agent"
    TOOLS = "tools"


class SessionKey(str, Enum):
    """
    Django session keys used by the chat feature.

    Centralising them here means renaming a key is a one-line change.
    """

    CHAT_HISTORY = "ai_chat_history"
    JWT_ACCESS = "jwt_access"
