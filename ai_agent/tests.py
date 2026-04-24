"""
Test suite for the ai_agent application.

Tools are tested against the real ORM (no mocking needed).
Views are tested with mocked retriever and agent to avoid
OpenAI / ChromaDB network calls.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from rest_framework_simplejwt.tokens import AccessToken

from contacts.models import Contact

from ai_agent.tools import (
    CreateContactTool,
    UpdateContactTool,
    DeleteContactTool,
    SearchContactsTool,
    build_tools,
)
from ai_agent.enums import SessionKey, ToolName, AgentNode
from ai_agent.views import _history_to_messages, _append_to_history


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(username: str = "agentuser", password: str = "testpass123") -> User:
    return User.objects.create_user(username=username, password=password)


def _make_contact(user: User, **kwargs) -> Contact:
    defaults = {"name": "John Doe", "phone": "1234567890"}
    defaults.update(kwargs)
    return Contact.objects.create(owner=user, **defaults)


def _jwt_for(user: User) -> str:
    return str(AccessToken.for_user(user))


def _set_session_jwt(client, user: User) -> None:
    token = _jwt_for(user)
    session = client.session
    session[SessionKey.JWT_ACCESS.value] = token
    session.save()


def _make_mock_agent(reply: str = "I can help you.") -> MagicMock:
    from langchain_core.messages import AIMessage
    agent = MagicMock()
    agent.invoke.return_value = {"messages": [AIMessage(content=reply)]}
    return agent


def _make_mock_retriever() -> MagicMock:
    retriever = MagicMock()
    retriever.invoke.return_value = []
    return retriever


# ─────────────────────────────────────────────────────────────────────────────
# Enum tests
# ─────────────────────────────────────────────────────────────────────────────

class EnumTest(TestCase):
    def test_tool_name_values(self):
        self.assertEqual(ToolName.CREATE_CONTACT, "create_contact")
        self.assertEqual(ToolName.UPDATE_CONTACT, "update_contact")
        self.assertEqual(ToolName.DELETE_CONTACT, "delete_contact")
        self.assertEqual(ToolName.SEARCH_CONTACTS, "search_contacts")

    def test_session_key_values(self):
        self.assertEqual(SessionKey.CHAT_HISTORY, "ai_chat_history")
        self.assertEqual(SessionKey.JWT_ACCESS, "jwt_access")

    def test_agent_node_values(self):
        self.assertEqual(AgentNode.RETRIEVE, "retrieve")
        self.assertEqual(AgentNode.AGENT, "agent")
        self.assertEqual(AgentNode.TOOLS, "tools")


# ─────────────────────────────────────────────────────────────────────────────
# Tool: CreateContactTool
# ─────────────────────────────────────────────────────────────────────────────

class CreateContactToolTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.tool = CreateContactTool(user=self.user)

    def test_creates_contact_in_db(self):
        result = self.tool._run(name="Alice", phone="555-0001")
        self.assertIn("Alice", result)
        self.assertIn("created successfully", result)
        self.assertTrue(Contact.objects.filter(owner=self.user, name="Alice").exists())

    def test_creates_with_optional_fields(self):
        result = self.tool._run(name="Bob", phone="555-0002", email="bob@test.com", address="123 St")
        self.assertIn("Bob", result)
        c = Contact.objects.get(owner=self.user, name="Bob")
        self.assertEqual(c.email, "bob@test.com")
        self.assertEqual(c.address, "123 St")

    def test_returns_id_in_message(self):
        result = self.tool._run(name="Carol", phone="555-0003")
        self.assertIn("ID:", result)

    def test_tool_name(self):
        self.assertEqual(self.tool.name, "create_contact")

    def test_build_tools_returns_four(self):
        tools = build_tools(self.user)
        self.assertEqual(len(tools), 4)
        names = {t.name for t in tools}
        self.assertIn("create_contact", names)
        self.assertIn("update_contact", names)
        self.assertIn("delete_contact", names)
        self.assertIn("search_contacts", names)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: UpdateContactTool
# ─────────────────────────────────────────────────────────────────────────────

class UpdateContactToolTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.tool = UpdateContactTool(user=self.user)

    def test_updates_name(self):
        c = _make_contact(self.user, name="Old Name")
        result = self.tool._run(contact_id=c.pk, name="New Name")
        self.assertIn("updated successfully", result)
        c.refresh_from_db()
        self.assertEqual(c.name, "New Name")

    def test_updates_phone(self):
        c = _make_contact(self.user)
        self.tool._run(contact_id=c.pk, phone="999-0000")
        c.refresh_from_db()
        self.assertEqual(c.phone, "999-0000")

    def test_contact_not_found(self):
        result = self.tool._run(contact_id=99999, name="X")
        self.assertIn("Failed", result)
        self.assertIn("not found", result)

    def test_no_fields_returns_helpful_message(self):
        c = _make_contact(self.user)
        result = self.tool._run(contact_id=c.pk)
        self.assertIn("No fields", result)

    def test_wrong_owner_returns_failure(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        result = self.tool._run(contact_id=c.pk, name="Hacked")
        self.assertIn("Failed", result)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: DeleteContactTool
# ─────────────────────────────────────────────────────────────────────────────

class DeleteContactToolTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.tool = DeleteContactTool(user=self.user)

    def test_deletes_contact(self):
        c = _make_contact(self.user)
        result = self.tool._run(contact_id=c.pk)
        self.assertIn("deleted", result)
        self.assertFalse(Contact.objects.filter(pk=c.pk).exists())

    def test_not_found_returns_failure(self):
        result = self.tool._run(contact_id=99999)
        self.assertIn("Failed", result)

    def test_wrong_owner_returns_failure(self):
        user2 = _make_user(username="other")
        c = _make_contact(user2)
        result = self.tool._run(contact_id=c.pk)
        self.assertIn("Failed", result)
        self.assertTrue(Contact.objects.filter(pk=c.pk).exists())


# ─────────────────────────────────────────────────────────────────────────────
# Tool: SearchContactsTool
# ─────────────────────────────────────────────────────────────────────────────

class SearchContactsToolTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.tool = SearchContactsTool(user=self.user)
        _make_contact(self.user, name="Alice Smith", phone="1111", email="alice@test.com")
        _make_contact(self.user, name="Bob Jones", phone="2222")

    def test_search_all_returns_all(self):
        result = self.tool._run()
        self.assertIn("Alice Smith", result)
        self.assertIn("Bob Jones", result)

    def test_search_by_q(self):
        result = self.tool._run(q="Alice")
        self.assertIn("Alice Smith", result)
        self.assertNotIn("Bob Jones", result)

    def test_no_results_message(self):
        result = self.tool._run(q="zzz_no_match")
        self.assertIn("No contacts found", result)

    def test_user_isolation(self):
        user2 = _make_user(username="other")
        _make_contact(user2, name="Charlie Secret")
        result = self.tool._run()
        self.assertNotIn("Charlie Secret", result)

    def test_result_contains_id_and_phone(self):
        result = self.tool._run(q="Alice")
        self.assertIn("ID", result)
        self.assertIn("1111", result)


# ─────────────────────────────────────────────────────────────────────────────
# View helper functions
# ─────────────────────────────────────────────────────────────────────────────

class HistoryToMessagesTest(TestCase):
    def test_user_message_becomes_human_message(self):
        from langchain_core.messages import HumanMessage
        result = _history_to_messages([{"role": "user", "content": "Hello"}])
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], HumanMessage)
        self.assertEqual(result[0].content, "Hello")

    def test_assistant_message_becomes_ai_message(self):
        from langchain_core.messages import AIMessage
        result = _history_to_messages([{"role": "assistant", "content": "Hi there"}])
        self.assertIsInstance(result[0], AIMessage)

    def test_unknown_role_skipped(self):
        result = _history_to_messages([{"role": "system", "content": "ignored"}])
        self.assertEqual(len(result), 0)

    def test_empty_history(self):
        self.assertEqual(_history_to_messages([]), [])

    def test_mixed_history(self):
        from langchain_core.messages import HumanMessage, AIMessage
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        result = _history_to_messages(history)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], HumanMessage)
        self.assertIsInstance(result[1], AIMessage)


class AppendToHistoryTest(TestCase):
    def test_appends_user_and_assistant_entries(self):
        class FakeSession(dict):
            modified = False

        s = FakeSession()
        _append_to_history(s, "Hello", "Hi there")
        history = s[SessionKey.CHAT_HISTORY.value]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], {"role": "user", "content": "Hello"})
        self.assertEqual(history[1], {"role": "assistant", "content": "Hi there"})
        self.assertTrue(s.modified)

    def test_appends_to_existing_history(self):
        class FakeSession(dict):
            modified = False

        s = FakeSession({SessionKey.CHAT_HISTORY.value: [{"role": "user", "content": "prev"}]})
        _append_to_history(s, "New msg", "New reply")
        self.assertEqual(len(s[SessionKey.CHAT_HISTORY.value]), 3)


# ─────────────────────────────────────────────────────────────────────────────
# AI Agent Views
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ChatPageViewTest(TestCase):
    def test_get_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/ai/")
        self.assertEqual(resp.status_code, 302)

    def test_get_authenticated_renders_chat(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.get("/ai/")
        self.assertEqual(resp.status_code, 200)

    def test_get_clears_chat_history_on_load(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        session = self.client.session
        session[SessionKey.CHAT_HISTORY.value] = [{"role": "user", "content": "old"}]
        session.save()
        self.client.get("/ai/")
        self.assertNotIn(SessionKey.CHAT_HISTORY.value, self.client.session)


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ClearChatViewTest(TestCase):
    def test_post_clears_history(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        session = self.client.session
        session[SessionKey.CHAT_HISTORY.value] = [{"role": "user", "content": "msg"}]
        session.save()
        resp = self.client.post("/ai/clear/", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(SessionKey.CHAT_HISTORY.value, self.client.session)

    def test_post_returns_ok_true(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post("/ai/clear/", content_type="application/json")
        data = json.loads(resp.content)
        self.assertTrue(data["ok"])


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
class ChatApiViewTest(TestCase):
    def test_post_unauthenticated_returns_401(self):
        resp = self.client.post(
            "/ai/chat/",
            json.dumps({"message": "hello"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_post_invalid_json_returns_400(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post("/ai/chat/", "not json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_post_empty_message_returns_400(self):
        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post(
            "/ai/chat/",
            json.dumps({"message": "   "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    @patch("ai_agent.views.build_agent")
    @patch("ai_agent.views.get_retriever")
    def test_post_success_returns_response(self, mock_retriever, mock_build_agent):
        mock_retriever.return_value = _make_mock_retriever()
        mock_build_agent.return_value = _make_mock_agent("Hello from AI!")

        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post(
            "/ai/chat/",
            json.dumps({"message": "Hello"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("response", data)
        self.assertEqual(data["response"], "Hello from AI!")

    @patch("ai_agent.views.build_agent")
    @patch("ai_agent.views.get_retriever")
    def test_post_saves_to_chat_history(self, mock_retriever, mock_build_agent):
        mock_retriever.return_value = _make_mock_retriever()
        mock_build_agent.return_value = _make_mock_agent("AI reply")

        user = _make_user()
        _set_session_jwt(self.client, user)
        self.client.post(
            "/ai/chat/",
            json.dumps({"message": "Test message"}),
            content_type="application/json",
        )
        history = self.client.session.get(SessionKey.CHAT_HISTORY.value, [])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "Test message")
        self.assertEqual(history[1]["role"], "assistant")

    @patch("ai_agent.views.build_agent")
    @patch("ai_agent.views.get_retriever")
    def test_post_agent_exception_returns_500(self, mock_retriever, mock_build_agent):
        mock_retriever.return_value = _make_mock_retriever()
        mock_build_agent.side_effect = Exception("Agent crash")

        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post(
            "/ai/chat/",
            json.dumps({"message": "Hello"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 500)
        data = json.loads(resp.content)
        self.assertIn("error", data)

    @patch("ai_agent.views.build_agent")
    @patch("ai_agent.views.get_retriever")
    def test_post_missing_message_key_returns_400(self, mock_retriever, mock_build_agent):
        mock_retriever.return_value = _make_mock_retriever()
        mock_build_agent.return_value = _make_mock_agent()

        user = _make_user()
        _set_session_jwt(self.client, user)
        resp = self.client.post(
            "/ai/chat/",
            json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
