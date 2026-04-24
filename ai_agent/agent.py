"""
LangGraph agent graph for the Contact Book AI assistant.

Graph topology:
    START → retrieve → agent → (tool call?) → tools → agent → … → END

- ``retrieve``:  fetch relevant policy chunks from ChromaDB and inject
                 them into the agent's system prompt.
- ``agent``:     GPT-4o LLM call; may emit tool-call messages.
- ``tools``:     LangGraph ``ToolNode`` that executes the chosen tool
                 and appends the result message to the state.

The graph loops between ``agent`` and ``tools`` until the LLM stops
emitting tool calls, then exits to END.
"""

from __future__ import annotations

from typing import Annotated, Any

from django.contrib.auth.models import User
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from .enums import AgentNode
from .tools import build_tools

# ─────────────────────────────────────────────────────────────────────────────
# State definition
# ─────────────────────────────────────────────────────────────────────────────


class GraphState(TypedDict):
    """
    Immutable snapshot passed between every node in the graph.

    Attributes:
        messages: Accumulated conversation messages.  ``add_messages``
                  reducer appends new messages rather than replacing the list.
        context:  RAG context injected by the ``retrieve`` node.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    context: str


# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE: str = """\
You are a helpful AI assistant for **Contact Book**, a personal phonebook app.

## What you can do
- Create new contacts (name + phone required; email and address optional)
- Update existing contacts by their numeric ID
- Delete contacts permanently by their numeric ID
- Search contacts by name, phone, email, or address

## Rules
- Always act on behalf of the currently authenticated user only.
- Before deleting, confirm the correct contact by searching first if the
  user has not provided a numeric ID.
- After every action, confirm what you did in a friendly, concise message.
- If you cannot find a contact, say so clearly and offer to search again.
- Keep answers short and focused on the phonebook task.
- **Phone numbers**: accept ANY string the user provides as the phone number —
  do NOT validate length, format, or country code. Never ask the user to
  correct or reformat a phone number. Save it exactly as given.
- **Act immediately**: if the user provides a name and a phone number, call
  create_contact right away without asking for confirmation.
- **Respect confirmations**: if the user says "yes", "save it", "confirm",
  "va bene", or any similar affirmation, call the tool immediately with the
  data from the most recent request — do not ask again.

## Relevant app knowledge
{context}
"""


def _build_system_prompt(context: str) -> str:
    """
    Render the system prompt with the RAG-retrieved context filled in.

    Args:
        context: Concatenated text of the top-K retrieved documents.

    Returns:
        A fully-rendered system prompt string.
    """
    return _SYSTEM_PROMPT_TEMPLATE.format(context=context or "No additional context.")


# ─────────────────────────────────────────────────────────────────────────────
# Graph node builders (closures that capture user + retriever)
# ─────────────────────────────────────────────────────────────────────────────


def _make_retrieve_node(
    retriever: VectorStoreRetriever,
) -> Any:
    """
    Return a ``retrieve`` node function that fetches RAG context.

    The retriever is captured via closure so the node function matches
    LangGraph's ``(state) -> dict`` signature.

    Args:
        retriever: Pre-built ChromaDB retriever.

    Returns:
        A callable ``(GraphState) -> dict`` for use as a graph node.
    """

    def retrieve(state: GraphState) -> dict[str, Any]:
        """
        Pull the last human message and retrieve relevant document chunks.

        Returns a dict that updates only the ``context`` key of the state.
        """
        human_messages: list[HumanMessage] = [
            m for m in state["messages"] if isinstance(m, HumanMessage)
        ]
        query: str = human_messages[-1].content if human_messages else ""
        docs = retriever.invoke(query)
        context: str = "\n\n".join(doc.page_content for doc in docs)
        return {"context": context}

    return retrieve


def _make_agent_node(llm_with_tools: Any) -> Any:
    """
    Return an ``agent`` node function that calls the LLM.

    Args:
        llm_with_tools: A ChatOpenAI model with tools already bound.

    Returns:
        A callable ``(GraphState) -> dict`` for use as a graph node.
    """

    def agent(state: GraphState) -> dict[str, Any]:
        """
        Invoke the LLM with the full message history + system prompt.

        The system message is prepended on every turn so the LLM always
        has the latest RAG context and instructions.
        """
        system = SystemMessage(content=_build_system_prompt(state.get("context", "")))
        messages_with_system: list[BaseMessage] = [system] + list(state["messages"])
        response: BaseMessage = llm_with_tools.invoke(messages_with_system)
        return {"messages": [response]}

    return agent


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────


def build_agent(user: User, retriever: VectorStoreRetriever) -> Any:
    """
    Compile and return a runnable LangGraph agent for *user*.

    The agent is re-created per request so each user session gets its
    own isolated tool set (tools carry the user reference in a closure).

    Args:
        user:      Authenticated Django ``User`` — passed to every tool.
        retriever: ChromaDB retriever for RAG context injection.

    Returns:
        A compiled ``CompiledGraph`` that accepts ``{"messages": [...],
        "context": ""}`` and returns an updated ``GraphState``.
    """
    from django.conf import settings

    tools = build_tools(user)

    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        openai_api_key=settings.OPENAI_API_KEY,
    )
    llm_with_tools = llm.bind_tools(tools)

    tool_node = ToolNode(tools)

    graph: StateGraph = StateGraph(GraphState)

    # Register nodes
    graph.add_node(AgentNode.RETRIEVE, _make_retrieve_node(retriever))
    graph.add_node(AgentNode.AGENT, _make_agent_node(llm_with_tools))
    graph.add_node(AgentNode.TOOLS, tool_node)

    # Wire edges
    graph.add_edge(START, AgentNode.RETRIEVE)
    graph.add_edge(AgentNode.RETRIEVE, AgentNode.AGENT)
    graph.add_conditional_edges(
        AgentNode.AGENT,
        tools_condition,
        {"tools": AgentNode.TOOLS, END: END},
    )
    graph.add_edge(AgentNode.TOOLS, AgentNode.AGENT)

    return graph.compile()
