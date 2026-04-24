"""
AppConfig for the ai_agent application.

Responsibility: register the app with Django and warm up the RAG
retriever once at startup so the first request does not pay the
embedding-index build cost.
"""

from __future__ import annotations

from django.apps import AppConfig


class AiAgentConfig(AppConfig):
    """Django application configuration for the AI agent feature."""

    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "ai_agent"
    verbose_name: str = "AI Agent"

    def ready(self) -> None:
        """
        Warm up the RAG retriever when Django starts.

        Skipped during management commands that run before the database is
        ready (e.g. migrate) to avoid import side-effects.
        """
        import sys

        # Do not initialise during migrations or other management commands
        # that do not need the vector store.
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return

        try:
            from .rag import get_retriever  # noqa: F401 — triggers lazy init

            get_retriever()
        except Exception:
            # Never crash Django startup because of RAG initialisation errors.
            pass
