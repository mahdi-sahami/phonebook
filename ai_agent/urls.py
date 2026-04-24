"""
URL patterns for the AI agent application.

Endpoints:
    GET  /ai/          → ChatPageView   (standalone chat page)
    POST /ai/chat/     → ChatApiView    (process one message)
    POST /ai/clear/    → ClearChatView  (wipe session history)
"""

from __future__ import annotations

from django.urls import path

from .views import ChatApiView, ChatPageView, ClearChatView

app_name: str = "ai_agent"

urlpatterns = [
    path("", ChatPageView.as_view(), name="chat_page"),
    path("chat/", ChatApiView.as_view(), name="chat_api"),
    path("clear/", ClearChatView.as_view(), name="clear_chat"),
]
