# workflows/investigator.py

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from diachronic_agents.llm.passage_classifier import (
    create_investigator_llm,
)
from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.tools.passage_tools import build_passage_tools
from diachronic_agents.workflows.investigation_record import build_investigation_record
from diachronic_agents.workflows.investigation_context import compact_investigation_context
from diachronic_agents.llm.request_budget import (
    INVESTIGATOR_MAX_OUTPUT_TOKENS,
    GroqRequestBudget,
    investigator_request_budget,
)


SYSTEM_PROMPT = """
You are a research investigator working with a historical text corpus.

Your task is to investigate the user's research question using the
available corpus tools and produce an evidence-led answer.

Research method:

1. Begin by identifying the concepts and historical periods relevant
   to the question.
2. Use semantic search to discover passages expressing relevant ideas.
3. Inspect promising passages before relying on them as evidence.
4. Use further semantic searches, passage-seeded searches, and lexical
   searches when the evidence suggests useful avenues of investigation.
5. Follow unexpected but potentially relevant findings when they can
   help answer the research question.
6. Compare evidence across periods where appropriate.

Evidence and provenance:

- Base historical claims on passages actually returned by the tools.
- Refer to evidence using its passage ID, publication year, title,
  author, and corpus metadata where available.
- Distinguish direct evidence from interpretation and hypothesis.
- Do not invent quotations, dates, bibliographic details, or passage IDs.
- A semantic match is a lead for investigation, not proof of a claim.
- A lexical match establishes wording, not necessarily meaning.
- If evidence is weak, contradictory, or absent, say so.
- Do not imply that the corpus is exhaustive.

Work autonomously within the available tool-call budget. Do not ask the
user to approve individual searches.

When you have investigated sufficiently, provide a structured answer:
- Findings
- Supporting passages
- Interpretation
- Limitations and unresolved questions

Be explicit about what the corpus evidence establishes and what remains
uncertain.
"""


class InvestigatorState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_call_count: int
    max_tool_calls: int


def build_investigator_workflow(
    retriever: PassageRetriever,
    *,
    llm: Any | None = None,
    checkpointer: Any | None = None,
    request_budget: GroqRequestBudget | None = None,
):
    """Build the corpus research investigator graph."""

    tools: list[BaseTool] = build_passage_tools(retriever)
    request_budget = request_budget or investigator_request_budget
    llm = llm or create_investigator_llm()
    model_with_tools = llm.bind_tools(tools)

    tool_node = ToolNode(tools)

    def call_model(state: InvestigatorState) -> dict:
        model_messages = compact_investigation_context(
            state["messages"]
        )

        request_budget.reserve(
            model_messages,
            tools=tools,
            max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        )

        response = model_with_tools.invoke(model_messages)
        return {"messages": [response]}
        
    def call_tools(state: InvestigatorState) -> dict:
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls

        result = tool_node.invoke({
            "messages": state["messages"],
        })

        return {
            "messages": result["messages"],
            "tool_call_count": (
                state["tool_call_count"] + len(tool_calls)
            ),
        }

    def finalize(state: InvestigatorState) -> dict:
        # Exclude the unexecuted tool-call request that triggered finalisation.
        messages = compact_investigation_context(
            state["messages"][:-1]
        )

        messages.append(
            HumanMessage(
                content=(
                    "The investigation has reached its tool-call budget. "
                    "Do not request further tools. Produce the best "
                    "evidence-led answer possible from the results already "
                    "collected. State any limitations caused by the budget."
                )
            )
        )

        request_budget.reserve(
            messages,
            max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        )

        response = llm.invoke(messages)
        return {"messages": [response]}
    
    def route_after_model(state: InvestigatorState) -> str:
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", [])

        if not tool_calls:
            return END

        if (
            state["tool_call_count"] + len(tool_calls)
            > state["max_tool_calls"]
        ):
            return "finalize"

        return "tools"

    graph = StateGraph(InvestigatorState)

    graph.add_node("agent", call_model)
    graph.add_node("tools", call_tools)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "agent")

    graph.add_conditional_edges(
        "agent",
        route_after_model,
        {
            "tools": "tools",
            "finalize": "finalize",
            END: END,
        },
    )

    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)

    return graph.compile(
        checkpointer=checkpointer or InMemorySaver()
    )


def run_investigation(
    question: str,
    *,
    retriever: PassageRetriever | None = None,
    workflow: Any | None = None,
    max_tool_calls: int = 12,
    thread_id: str | None = None,
) -> dict:
    """Run a corpus investigation and return its complete graph state."""

    if not question.strip():
        raise ValueError("question must not be empty")

    if not 1 <= max_tool_calls <= 100:
        raise ValueError("max_tool_calls must be between 1 and 100")

    if workflow is None:
        if retriever is None:
            raise ValueError(
                "A PassageRetriever is required when no workflow is supplied"
            )

        workflow = build_investigator_workflow(retriever)

    state: InvestigatorState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ],
        "tool_call_count": 0,
        "max_tool_calls": max_tool_calls,
    }

    result = workflow.invoke(
        state,
        config={
            "configurable": {
                "thread_id": thread_id or str(uuid4()),
            },
            "recursion_limit": (max_tool_calls * 2) + 5,
        },
    )

    result["investigation_record"] = build_investigation_record(result)

    return result
