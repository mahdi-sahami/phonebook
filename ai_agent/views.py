"""
Django views for the AI agent chat feature.

Three views:
- ``ChatPageView``  — GET: render the standalone chat page.
- ``ChatApiView``   — POST: process one user message and return the AI reply.
- ``ClearChatView`` — POST: wipe the session chat history.

Conversation history is stored in ``request.session`` (ephemeral):
- It lives only for the duration of the browser session.
- It is scoped per Django session (i.e. per user).
- It is automatically destroyed when the user logs out or the session
  cookie expires.
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from contacts.services import get_user_from_token
import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)

from .agent import build_agent
from .enums import SessionKey
from .rag import get_retriever


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_authenticated_user(request: HttpRequest) -> User | None:
    """
    Retrieve the authenticated user from the JWT stored in the session.

    Returns:
        The ``User`` instance, or ``None`` if the token is missing / invalid.
    """
    token: str | None = request.session.get(SessionKey.JWT_ACCESS.value)
    if not token:
        return None
    return get_user_from_token(token)


def _history_to_messages(
    history: list[dict[str, str]],
) -> list[BaseMessage]:
    """
    Convert the session-serialised chat history to LangChain message objects.

    The history is stored as a list of ``{"role": "user"|"assistant",
    "content": "..."}`` dicts so it can be JSON-serialised in the session.

    Args:
        history: Session chat history list.

    Returns:
        A list of ``HumanMessage`` / ``AIMessage`` instances.
    """
    messages: list[BaseMessage] = []
    for entry in history:
        role: str = entry.get("role", "")
        content: str = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _append_to_history(
    session: Any,
    user_message: str,
    ai_reply: str,
) -> None:
    """
    Append a user/assistant exchange to the session chat history.

    Creates the history list if it does not yet exist, then marks the
    session as modified so Django persists the change.

    Args:
        session:      The Django session object.
        user_message: The user's latest message.
        ai_reply:     The AI assistant's reply.
    """
    history: list[dict[str, str]] = session.get(SessionKey.CHAT_HISTORY.value, [])
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": ai_reply})
    session[SessionKey.CHAT_HISTORY.value] = history
    session.modified = True


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────


class ChatPageView(View):
    """
    Render the standalone AI chat page.

    Redirects unauthenticated visitors to the login page.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        """Return the chat HTML template."""
        user: User | None = _get_authenticated_user(request)
        if user is None:
            from django.shortcuts import redirect

            return redirect("contacts_templates:login")
        # Clear history on every page load so a fresh visit is never
        # contaminated by a previous conversation's context.
        request.session.pop(SessionKey.CHAT_HISTORY.value, None)
        request.session.modified = True
        return render(request, "ai_agent/chat.html", {"username": user.username})


@method_decorator(csrf_exempt, name="dispatch")
class ChatApiView(View):
    """
    Process a single chat message and return the AI reply as JSON.

    Expects a POST body: ``{"message": "user text here"}``
    Returns: ``{"response": "AI reply text"}`` or ``{"error": "..."}``

    Conversation history is persisted in the Django session between
    requests and cleared automatically on logout.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        """Handle one user message → AI response cycle."""
        # ── Auth ──────────────────────────────────────────────────────────
        user: User | None = _get_authenticated_user(request)
        if user is None:
            return JsonResponse(
                {"error": "Not authenticated. Please log in first."},
                status=401,
            )

        # ── Parse body ────────────────────────────────────────────────────
        try:
            body: dict[str, Any] = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        message: str = str(body.get("message", "")).strip()
        if not message:
            return JsonResponse({"error": "Message cannot be empty."}, status=400)

        # ── Build message history ──────────────────────────────────────────
        # Limit to the last 6 session entries (3 user/assistant pairs) so old
        # "please confirm your phone number" loops can't trap the model.
        _HISTORY_WINDOW = 6
        raw_history: list[dict[str, str]] = request.session.get(
            SessionKey.CHAT_HISTORY.value, []
        )[-_HISTORY_WINDOW:]
        prior_messages: list[BaseMessage] = _history_to_messages(raw_history)
        current_message: HumanMessage = HumanMessage(content=message)
        all_messages: list[BaseMessage] = prior_messages + [current_message]

        # ── Run agent ──────────────────────────────────────────────────────
        try:
            retriever = get_retriever()
            agent = build_agent(user=user, retriever=retriever)
            result: dict[str, Any] = agent.invoke(
                {"messages": all_messages, "context": ""}
            )
        except Exception as exc:
            return JsonResponse(
                {"error": f"Agent error: {exc}"},
                status=500,
            )

        # ── Extract reply ──────────────────────────────────────────────────
        # Message order in result["messages"]:
        #   … HumanMessage → AIMessage(tool_calls, content="") → ToolMessage
        #     → AIMessage(final, content="actual reply")
        #
        # Step 1: find the last AIMessage that is a FINAL response (no tool_calls).
        # Step 2: if still empty, use the last ToolMessage (tool result is readable).
        # Step 3: fall back to a generic error string.
        # Always log the full chain so the root cause can be investigated.

        def _extract_text(content: Any) -> str:
            """Return non-empty string from a message's content, or ''."""
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = [
                    block["text"]
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and block.get("text")
                ]
                return "\n".join(parts).strip()
            return ""

        ai_reply: str = ""

        # Step 1 — last non-empty final AIMessage (no tool_calls)
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                text = _extract_text(msg.content)
                if text:
                    ai_reply = text
                    break

        # Step 2 — last ToolMessage result (meaningful on its own)
        if not ai_reply:
            for msg in reversed(result["messages"]):
                if isinstance(msg, ToolMessage):
                    text = _extract_text(msg.content)
                    if text:
                        ai_reply = text
                        break

        # Always log the message chain to aid debugging
        logger.debug(
            "Agent message chain: %s",
            [
                "%s(tool_calls=%s, content=%r)"
                % (
                    type(m).__name__,
                    bool(getattr(m, "tool_calls", None)),
                    m.content[:60] if isinstance(m.content, str) else m.content,
                )
                for m in result["messages"]
            ],
        )

        if not ai_reply:
            logger.warning(
                "Agent returned no usable reply. Full chain: %s",
                [type(m).__name__ + ": " + repr(m.content)[:80] for m in result["messages"]],
            )
            ai_reply = "I processed your request but couldn't generate a reply. Please try again."

        # ── Persist history ────────────────────────────────────────────────
        _append_to_history(request.session, message, ai_reply)

        return JsonResponse({"response": ai_reply})


@method_decorator(csrf_exempt, name="dispatch")
class ClearChatView(View):
    """
    Wipe the current user's session chat history.

    Called when the user clicks the "Clear chat" button in the UI.
    """

    def post(self, request: HttpRequest) -> JsonResponse:
        """Delete the chat history key from the session."""
        request.session.pop(SessionKey.CHAT_HISTORY.value, None)
        request.session.modified = True
        return JsonResponse({"ok": True})
