"""
Retrieval-Augmented Generation (RAG) setup for the AI agent.

Responsibilities (SOC):
- Load and chunk the knowledge-base markdown file.
- Build / reuse the ChromaDB vector store.
- Expose a retriever that the agent graph can call.

Chunking strategy: simple paragraph split (``\\n\\n`` boundary).
This is intentional — the knowledge base is a short policy document,
not a large corpus, so recursive or semantic chunking would add
complexity without meaningful benefit.

Embedding model: ``text-embedding-3-small`` (OpenAI).
Small, fast, cheap — appropriate for a phonebook chatbot.
"""

from __future__ import annotations

import pathlib
import threading
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (lazy, thread-safe)
# ─────────────────────────────────────────────────────────────────────────────

_retriever: Optional[VectorStoreRetriever] = None
_lock = threading.Lock()

KNOWLEDGE_BASE_PATH: pathlib.Path = (
    pathlib.Path(__file__).resolve().parent.parent
    / "knowledge_base"
    / "phonebook_policies.md"
)

COLLECTION_NAME: str = "phonebook_policies"
EMBEDDING_MODEL: str = "text-embedding-3-small"
TOP_K: int = 3


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _load_documents() -> list[Document]:
    """
    Read the knowledge-base file and split it into paragraph chunks.

    Each non-empty paragraph separated by a blank line becomes its own
    ``Document``.  Simple chunking is sufficient here because the
    knowledge base is short and well-structured.

    Returns:
        A list of ``Document`` objects, one per paragraph.
    """
    text: str = KNOWLEDGE_BASE_PATH.read_text(encoding="utf-8")
    paragraphs: list[str] = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [
        Document(page_content=paragraph, metadata={"source": "phonebook_policies.md"})
        for paragraph in paragraphs
    ]


def _build_vector_store() -> VectorStoreRetriever:
    """
    Build (or connect to) the ChromaDB vector store and return a retriever.

    Behaviour:
    - If ``CHROMA_HOST`` is configured in Django settings, connects to a
      remote ChromaDB container (Docker / production).
    - Otherwise falls back to a local persistent directory
      (``CHROMA_PERSIST_DIR`` setting, defaults to ``./chroma_db``).

    Returns:
        A configured ``VectorStoreRetriever`` that returns the top-K most
        relevant document chunks for a given query.
    """
    from django.conf import settings
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
    )

    chroma_host: str = getattr(settings, "CHROMA_HOST", "")
    chroma_port: int = getattr(settings, "CHROMA_PORT", 8001)
    persist_dir: str = getattr(settings, "CHROMA_PERSIST_DIR", "./chroma_db")

    if chroma_host:
        # Remote ChromaDB (Docker Compose service)
        import chromadb

        http_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        vector_store = Chroma(
            client=http_client,
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
        )
        # Populate the collection if it is empty
        if vector_store._collection.count() == 0:
            docs = _load_documents()
            vector_store.add_documents(docs)
    else:
        # Local persistent ChromaDB (development / no Docker)
        docs = _load_documents()
        vector_store = Chroma.from_documents(
            documents=docs,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=persist_dir,
        )

    return vector_store.as_retriever(search_kwargs={"k": TOP_K})


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def get_retriever() -> VectorStoreRetriever:
    """
    Return the module-level RAG retriever, initialising it on first call.

    Thread-safe: uses a lock so the vector store is only built once even
    under concurrent startup.

    Returns:
        A ``VectorStoreRetriever`` configured for ``TOP_K`` results.
    """
    global _retriever

    if _retriever is not None:
        return _retriever

    with _lock:
        # Double-checked locking pattern
        if _retriever is None:
            _retriever = _build_vector_store()

    return _retriever
