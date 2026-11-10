from __future__ import annotations

import json
import time
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from mutatis_mutandis.lib.corpus_logging import get_logger

from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.tools.passage_tools import build_passage_tools
from diachronic_agents.workflows.investigation_record import (
    build_investigation_record,
)
from diachronic_agents.llm.request_budget import (
    INVESTIGATOR_MAX_OUTPUT_TOKENS,
    GroqRequestBudget,
    GroqTokenBudgetExceeded,
    investigator_request_budget,
)
from diachronic_agents.workflows.investigation_context import (
    compact_investigation_context,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLANNER_PROMPT = """
You are planning a historical corpus investigation.

Given the research question and chronological coverage, produce a concise
research plan containing:

- The principal concepts and distinctions to investigate.
- Useful search vocabulary, including historical variants where relevant.
- What evidence would support or weaken the proposed interpretation.
- Potential ambiguities, false positives, and control cases.
- Questions that should be compared across chronological periods.

Do not answer the research question yet.
Do not invent corpus findings.
Keep the plan concise and operational.
"""


PERIOD_PROMPT = """
You are a historical corpus investigator working on one chronological period.

Investigate the research question using the available corpus tools.

Research method:

1. Search semantically for relevant passages in the assigned period.
2. Inspect promising results before treating them as evidence.
3. Evaluate inspected passages against the research question.
4. Refine searches or use search_from_passage to follow relevant
   connections when useful.
5. Pursue unexpected findings only when they may illuminate the question.
6. Distinguish direct evidence from interpretation and hypothesis.
7. Do not treat semantic similarity as proof.
8. Do not invent quotations, dates, passage IDs, or bibliographic details.

You are working on ONE period, not the entire chronology.

The research plan and summaries of preceding periods are context, not
evidence for claims about this period.

Use the tools adaptively. You do not need to inspect every search result.
When you have investigated sufficiently, explain what you found and
identify the passage IDs supporting your observations.

If evidence is weak or absent, say so.

Do not attempt to investigate other chronological periods.
"""


PERIOD_SUMMARY_PROMPT = """
You are interpreting the audit record of a historical corpus investigation.

The supplied tool calls and results are a bounded, structured projection
of the authoritative audit record. They show what was searched, retrieved
and inspected during the specified period.

Produce a concise, structured research summary for that period.

Include:

- Principal findings, if supported by inspected passages.
- Supporting passage IDs.
- What the inspected passages actually establish.
- Interpretations and hypotheses, clearly distinguished from observations.
- Contradictory or ambiguous evidence.
- Important absences and limitations.
- Useful follow-up questions.

Evidence rules:

1. Do not claim a search was performed unless it appears in tool_calls.
2. Do not claim a passage was inspected unless it appears in
   inspected_passages or an inspection tool call with a successful result.
3. Search candidates are leads, not inspected evidence.
4. A search returning zero results is not proof that the phenomenon
   is absent from the period or corpus.
5. Distinguish zero search results from search results that were not
   inspected.
6. Do not invent quotations, dates, passage IDs or bibliographic details.
7. Do not infer that the corpus lacks coverage merely because a search
   returned no results.
8. The budget object and activity counts are authoritative.
9. If the tool-call budget was exhausted, describe the investigation
   as incomplete, even if some passages were inspected.
10. Do not turn a lack of investigation into a negative finding.
11. Do not treat a failed inspection call as a successful inspection.

Keep the summary concise and evidence-led.
"""


SYNTHESIS_PROMPT = """
You are synthesising a chronological historical corpus investigation.

Use the research question, plan, period summaries, and inspected
passages supplied below.

Produce an evidence-led answer with:

1. Findings
2. Supporting passages, with passage IDs and bibliographic metadata
   where available
3. Chronological developments or differences between periods
4. Interpretation
5. Contradictions, uncertainties, and limitations
6. Further research questions

Distinguish direct textual evidence from interpretation and hypothesis.

Do not invent quotations, dates, bibliographic details, or passage IDs.
Do not imply that the corpus is exhaustive.

Periods marked as uninvestigated or budget-exhausted provide no
evidence and must not be treated as negative findings.
"""


# ---------------------------------------------------------------------------
# Chronological periods
# ---------------------------------------------------------------------------

def make_periods(
    *,
    start_year: int,
    end_year: int,
    period_size: int = 100,
) -> list[dict[str, Any]]:
    """Create inclusive chronological periods."""

    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")

    if period_size < 1:
        raise ValueError("period_size must be positive")

    periods = []
    start = start_year

    while start <= end_year:
        end = min(start + period_size - 1, end_year)

        periods.append({
            "start_year": start,
            "end_year": end,
            "label": f"{start}–{end}",
        })

        start = end + 1

    return periods


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class InvestigatorState(TypedDict):
    # Complete audit history
    messages: Annotated[list[AnyMessage], add_messages]

    question: str
    plan: str

    periods: list[dict[str, Any]]
    period_index: int

    # Compactable working context for the current period
    period_messages: list[AnyMessage]

    # Append-only audit trail for the current period
    period_audit_messages: list[AnyMessage]

    period_summaries: list[dict[str, Any]]

    tool_call_count: int
    period_tool_call_count: int
    max_tool_calls: int
    max_period_tool_calls: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_text(message: AIMessage) -> str:
    """Extract readable model content."""

    content = message.content

    if isinstance(content, str):
        return content

    return json.dumps(content, ensure_ascii=False, default=str)


def _decode_tool_result(content: Any) -> Any:
    """Decode a JSON-encoded tool result where possible."""

    if isinstance(content, (dict, list)):
        return content

    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_content": content}

    return {"raw_content": str(content)}


def _result_passages(result: Any) -> list[dict[str, Any]]:
    """
    Extract passage-shaped records from a decoded tool result.

    Search tools normally return a 'results' list. inspect_passage normally
    returns one passage directly.
    """

    if not isinstance(result, dict):
        return []

    passages = result.get("results")

    if isinstance(passages, list):
        return [
            item
            for item in passages
            if isinstance(item, dict)
            and item.get("passage_id") is not None
        ]

    if result.get("passage_id") is not None:
        return [result]

    return []


def _period_prompt(
    *,
    question: str,
    plan: str,
    period: dict[str, Any],
    previous_summaries: list[dict[str, Any]],
) -> str:
    """Build the initial working prompt for a chronological period."""

    previous = json.dumps(
        previous_summaries,
        ensure_ascii=False,
        default=str,
    )

    return f"""
RESEARCH QUESTION
{question}

RESEARCH PLAN
{plan}

CURRENT PERIOD
{period["label"]}
Start year: {period["start_year"]}
End year: {period["end_year"]}

PREVIOUS PERIOD SUMMARIES
{previous}

Investigate the current period only.
Use the research plan and preceding summaries to guide searches.
"""


def _inspect_evidence(
    messages: list[AnyMessage],
    *,
    max_passages: int = 12,
    max_chars_per_passage: int = 1800,
) -> list[dict[str, Any]]:
    """Extract inspected passage records for final synthesis."""

    evidence: dict[str, dict[str, Any]] = {}

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue

        if message.name != "inspect_passage":
            continue

        content = _decode_tool_result(message.content)

        if not isinstance(content, dict):
            continue

        for passage in _result_passages(content):
            passage_id = passage.get("passage_id")

            if passage_id is None:
                continue

            text = passage.get("text") or passage.get("excerpt")

            item = {
                key: passage.get(key)
                for key in (
                    "passage_id",
                    "corpus",
                    "doc_id",
                    "pub_year",
                    "title",
                    "author",
                    "scale",
                )
                if passage.get(key) is not None
            }

            if text:
                item["text"] = str(text)[:max_chars_per_passage]

            evidence[str(passage_id)] = item

    return list(evidence.values())[-max_passages:]


def _budget_exhausted_summaries(
    periods: list[dict[str, Any]],
    start_index: int,
) -> list[dict[str, Any]]:
    """Represent remaining periods without claiming findings."""

    return [
        {
            "period": period["label"],
            "status": "budget_exhausted",
            "activity": {
                "tool_call_count": 0,
                "search_count": 0,
                "search_result_count": 0,
                "inspection_count": 0,
                "inspected_passage_count": 0,
                "budget_exhausted": True,
            },
            "summary": (
                "Not investigated because the global tool-call "
                "budget was exhausted before this period began."
            ),
            "passage_ids": [],
            "warnings": [],
        }
        for period in periods[start_index:]
    ]


def _deterministic_period_summary(
    *,
    status: str,
    activity: dict[str, Any],
) -> str:
    """Create a factual fallback when a period cannot be summarised by an LLM."""

    if status == "not_investigated":
        return "The period was not investigated: no corpus tools were executed."

    if status == "searched_no_hits":
        return (
            f"{activity['search_count']} search call(s) were executed, "
            "but they returned no candidate passages. This does not "
            "establish that the phenomenon is absent from the corpus."
        )

    if status == "search_results_not_inspected":
        return (
            f"{activity['search_count']} search call(s) returned "
            f"{activity['search_result_count']} candidate result(s). "
            "No passage was successfully inspected, so these candidates "
            "cannot yet be treated as evidence."
        )

    if status == "inspected":
        return (
            f"{activity['inspected_passage_count']} distinct passage(s) "
            "were successfully inspected. The inspection records are "
            "preserved, but no model-generated interpretation is available."
        )

    if status == "budget_exhausted":
        return (
            "The period investigation reached its tool-call budget. "
            f"{activity['inspected_passage_count']} distinct passage(s) "
            "were successfully inspected, but the investigation may be "
            "incomplete."
        )

    return (
        f"{activity['tool_call_count']} tool call(s) were executed. "
        "No successfully inspected passage was recorded."
    )


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

def build_investigator_workflow(
    retriever: PassageRetriever,
    *,
    llm: BaseChatModel | None = None,
    plain_llm: BaseChatModel | None = None,
    checkpointer: Any | None = None,
    request_budget: GroqRequestBudget | None = None,
    max_period_tool_calls: int = 4,
):
    if llm is None:
        raise ValueError("llm must be a BaseChatModel instance")

    # Keep the tool-using model separate from ordinary text generation.
    # If no second model is supplied, retain the original single-model
    # behaviour for backwards compatibility.
    if plain_llm is None:
        plain_llm = llm

    if max_period_tool_calls < 1:
        raise ValueError("max_period_tool_calls must be positive")

    tools: list[BaseTool] = build_passage_tools(retriever)

    request_budget = request_budget or investigator_request_budget

    model_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(state: InvestigatorState) -> dict:
        messages = [
            SystemMessage(content=PLANNER_PROMPT),
            HumanMessage(
                content=(
                    f"Research question:\n{state['question']}\n\n"
                    f"Chronological coverage:\n"
                    f"{state['periods'][0]['label']} to "
                    f"{state['periods'][-1]['label']}\n\n"
                    f"Periods:\n"
                    f"{json.dumps(state['periods'], ensure_ascii=False)}"
                )
            ),
        ]

        request_budget.reserve(
            messages,
            max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        )

        started = time.monotonic()
        response = plain_llm.invoke(messages)

        logger.info(
            "Investigation plan received in %.2fs:\n%s",
            time.monotonic() - started,
            response.pretty_repr(),
        )

        return {
            "plan": _content_text(response),
            "messages": [response],
        }

    # ------------------------------------------------------------------
    # Begin period
    # ------------------------------------------------------------------

    def begin_period(state: InvestigatorState) -> dict:
        index = state["period_index"]
        period = state["periods"][index]

        period_messages = [
            SystemMessage(content=PERIOD_PROMPT),
            HumanMessage(
                content=_period_prompt(
                    question=state["question"],
                    plan=state["plan"],
                    period=period,
                    previous_summaries=state["period_summaries"],
                )
            ),
        ]

        logger.info(
            "Starting investigation period %s (%d/%d)",
            period["label"],
            index + 1,
            len(state["periods"]),
        )

        return {
            "period_messages": period_messages,
            "period_audit_messages": list(period_messages),
            "period_tool_call_count": 0,
        }

    # ------------------------------------------------------------------
    # Period investigator
    # ------------------------------------------------------------------

    def investigate_period(state: InvestigatorState) -> dict:
        messages = state["period_messages"]

        remaining_global = (
            state["max_tool_calls"] - state["tool_call_count"]
        )

        remaining_period = (
            state["max_period_tool_calls"]
            - state["period_tool_call_count"]
        )

        allowed_calls = max(
            0,
            min(remaining_global, remaining_period),
        )

        if allowed_calls == 0:
            response = AIMessage(
                content="Tool-call budget exhausted for this period."
            )

            return {
                "period_messages": [*messages, response],
                "messages": [response],
            }

        # Retain the initial instructions and question, together with
        # the most recent interaction and relevant inspected evidence.
        context_messages = compact_investigation_context(
            messages,
            recent_rounds=1,
        )

        request_budget.reserve(
            context_messages,
            tools=tools,
            max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
        )

        started = time.monotonic()
        response: AIMessage = model_with_tools.invoke(context_messages)
        elapsed = time.monotonic() - started

        # Prevent the model from executing a batch beyond its budget.
        if len(response.tool_calls) > allowed_calls:
            logger.warning(
                "Trimming tool-call batch from %d to %d",
                len(response.tool_calls),
                allowed_calls,
            )

            response = response.model_copy(
                update={
                    "tool_calls": response.tool_calls[:allowed_calls],
                }
            )

        logger.info(
            "Period investigator response received in %.2fs:\n%s",
            elapsed,
            response.pretty_repr(),
        )

        return {
            "period_messages": [*context_messages, response],
            "period_audit_messages": [
                *state["period_audit_messages"],
                response,
            ],
            "messages": [response],
        }

    # ------------------------------------------------------------------
    # Execute tools
    # ------------------------------------------------------------------

    def execute_period_tools(state: InvestigatorState) -> dict:
        last_message = state["period_messages"][-1]
        tool_calls = last_message.tool_calls

        for tool_call in tool_calls:
            logger.info(
                "Investigator calling tool: %s\nArguments:\n%s",
                tool_call["name"],
                json.dumps(
                    tool_call["args"],
                    indent=2,
                    ensure_ascii=False,
                ),
            )

        result = tool_node.invoke({
            "messages": state["period_messages"],
        })

        tool_messages = result["messages"]

        for message in tool_messages:
            logger.debug(
                "Investigator tool result: %s\n%s",
                message.name,
                message.content,
            )

        return {
            "period_messages": [
                *state["period_messages"],
                *tool_messages,
            ],
            "period_audit_messages": [
                *state["period_audit_messages"],
                *tool_messages,
            ],
            "messages": tool_messages,
            "tool_call_count": (
                state["tool_call_count"] + len(tool_calls)
            ),
            "period_tool_call_count": (
                state["period_tool_call_count"] + len(tool_calls)
            ),
        }

    # ------------------------------------------------------------------
    # Period summary payload
    # ------------------------------------------------------------------

    def _period_summary_payload(
        record: dict[str, Any],
        *,
        question: str,
        plan_text: str,
        period: dict[str, Any],
        activity: dict[str, Any],
        budget_exhausted: bool,
        max_tool_calls: int,
        max_period_tool_calls: int,
        max_candidates: int = 12,
        max_inspected: int = 8,
    ) -> dict[str, Any]:
        """
        Build a bounded projection of the authoritative audit record.

        The full tool-call/result history remains in record. This payload
        selects a limited number of candidate excerpts and inspected
        passages for the summary model.
        """

        tool_calls = []
        search_candidates: dict[str, dict[str, Any]] = {}
        inspected_passages: dict[str, dict[str, Any]] = {}

        for call in record.get("tool_calls", []):
            tool_name = call.get("tool_name")
            result = call.get("result")
            result = _decode_tool_result(result)

            if not isinstance(result, dict):
                result = {}

            passages = _result_passages(result)

            tool_calls.append({
                "tool_name": tool_name,
                "arguments": call.get("arguments", {}),
                "status": call.get("status"),
                "result_count": (
                    len(result.get("results", []))
                    if isinstance(result.get("results"), list)
                    else (
                        1 if result.get("passage_id") is not None
                        else None
                    )
                ),
                "result_passage_ids": [
                    str(item["passage_id"])
                    for item in passages[:5]
                ],
                "warnings": result.get("warnings", []),
            })

            if tool_name in {"semantic_search", "search_corpus"}:
                for passage in passages:
                    passage_id = passage.get("passage_id")

                    if passage_id is None:
                        continue

                    key = str(passage_id)

                    if key in search_candidates:
                        continue

                    excerpt = passage.get("text") or passage.get("excerpt") or ""

                    search_candidates[key] = {
                        "passage_id": key,
                        "pub_year": passage.get("pub_year"),
                        "title": passage.get("title"),
                        "author": passage.get("author"),
                        "excerpt": " ".join(str(excerpt).split())[:350],
                    }

                    if len(search_candidates) >= max_candidates:
                        break

            elif tool_name == "inspect_passage":
                for passage in passages:
                    passage_id = passage.get("passage_id")

                    if passage_id is None:
                        continue

                    key = str(passage_id)

                    text = passage.get("text") or passage.get("excerpt") or ""

                    inspected_passages[key] = {
                        "passage_id": key,
                        "pub_year": passage.get("pub_year"),
                        "title": passage.get("title"),
                        "author": passage.get("author"),
                        "text": " ".join(str(text).split())[:1200],
                    }

                    if len(inspected_passages) >= max_inspected:
                        break

        return {
            "research_question": question,
            "research_plan": plan_text,
            "period": {
                "label": period["label"],
                "start_year": period["start_year"],
                "end_year": period["end_year"],
            },
            "activity": activity,
            "budget": {
                "tool_call_budget_exhausted": budget_exhausted,
                "global_tool_calls_used": record.get("tool_call_count", 0),
                "global_tool_call_limit": max_tool_calls,
                "period_tool_call_limit": max_period_tool_calls,
            },
            "tool_calls": tool_calls,
            "search_candidates": list(search_candidates.values()),
            "inspected_passages": list(inspected_passages.values()),
            "warnings": record.get("warnings", []),
        }

    # ------------------------------------------------------------------
    # Period summary
    # ------------------------------------------------------------------

    def summarise_period(state: InvestigatorState) -> dict:
        period = state["periods"][state["period_index"]]

        # Build an authoritative record from this period's complete,
        # uncompacted tool-call and tool-result history.
        period_record = build_investigation_record({
            "messages": state["period_audit_messages"],
            "tool_call_count": state["period_tool_call_count"],
        })

        tool_calls = period_record.get("tool_calls", [])

        search_calls = [
            call
            for call in tool_calls
            if call.get("tool_name") in {
                "semantic_search",
                "search_corpus",
            }
        ]

        inspection_calls = [
            call
            for call in tool_calls
            if call.get("tool_name") == "inspect_passage"
        ]

        search_result_count = 0

        for call in search_calls:
            result = _decode_tool_result(call.get("result"))

            if isinstance(result, dict):
                results = result.get("results", [])

                if isinstance(results, list):
                    search_result_count += len(results)

        # Count only passages returned by successful inspection calls.
        inspected_passage_ids: set[str] = set()

        for call in inspection_calls:
            if call.get("status") != "success":
                continue

            result = _decode_tool_result(call.get("result"))

            for passage in _result_passages(result):
                passage_id = passage.get("passage_id")

                if passage_id is not None:
                    inspected_passage_ids.add(str(passage_id))

        budget_exhausted = (
            state["tool_call_count"] >= state["max_tool_calls"]
            or state["period_tool_call_count"]
            >= state["max_period_tool_calls"]
        )

        # Status describes what actually happened, not what the
        # summarisation model says happened.
        if budget_exhausted:
            status = "budget_exhausted"
        elif not tool_calls:
            status = "not_investigated"
        elif inspected_passage_ids:
            status = "inspected"
        elif search_result_count:
            status = "search_results_not_inspected"
        elif search_calls:
            status = "searched_no_hits"
        else:
            status = "tools_used_no_evidence"

        activity = {
            "tool_call_count": len(tool_calls),
            "search_count": len(search_calls),
            "search_result_count": search_result_count,
            "inspection_count": len(inspection_calls),
            "inspected_passage_count": len(inspected_passage_ids),
            "budget_exhausted": budget_exhausted,
        }

        warnings = list(period_record.get("warnings", []))

        # No LLM interpretation is needed when no tools were executed.
        if not tool_calls:
            summary_text = _deterministic_period_summary(
                status=status,
                activity=activity,
            )

        else:
            # Send a bounded, structured projection of the authoritative
            # audit. The complete tool calls/results remain in period_record.
            summary_input = _period_summary_payload(
                period_record,
                question=state["question"],
                plan_text=state["plan"],
                period=period,
                activity=activity,
                budget_exhausted=budget_exhausted,
                max_tool_calls=state["max_tool_calls"],
                max_period_tool_calls=state["max_period_tool_calls"],
            )

            messages = [
                SystemMessage(content=PERIOD_SUMMARY_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        summary_input,
                        ensure_ascii=False,
                        default=str,
                    )
                ),
            ]

            try:
                request_budget.reserve(
                    messages,
                    max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
                )

                response = plain_llm.invoke(messages)
                summary_text = _content_text(response)

                logger.info(
                    "Period summary for %s:\n%s",
                    period["label"],
                    summary_text,
                )

            except GroqTokenBudgetExceeded as exc:
                logger.warning(
                    "Summary request exceeded the Groq token budget "
                    "for period %s; using deterministic summary: %s",
                    period["label"],
                    exc,
                )

                warnings.append(
                    "LLM period summarisation was skipped because the "
                    "Groq request token budget was exceeded. The audit "
                    "record and activity counts are retained."
                )

                summary_text = _deterministic_period_summary(
                    status=status,
                    activity=activity,
                )

        summary = {
            "period": period["label"],
            "status": status,
            "activity": activity,
            "summary": summary_text,
            "passage_ids": sorted(inspected_passage_ids),
            "warnings": warnings,
        }

        logger.info(
            "Period %s: status=%s, activity=%s",
            period["label"],
            status,
            activity,
        )

        return {
            "period_summaries": [
                *state["period_summaries"],
                summary,
            ],
        }

    # ------------------------------------------------------------------
    # Advance chronological coverage
    # ------------------------------------------------------------------

    def advance_period(state: InvestigatorState) -> dict:
        next_index = state["period_index"] + 1

        if next_index >= len(state["periods"]):
            return {"period_index": next_index}

        if state["tool_call_count"] >= state["max_tool_calls"]:
            skipped = _budget_exhausted_summaries(
                state["periods"],
                next_index,
            )

            logger.warning(
                "Global tool-call budget exhausted; "
                "marking %d periods uninvestigated",
                len(skipped),
            )

            return {
                "period_index": len(state["periods"]),
                "period_summaries": [
                    *state["period_summaries"],
                    *skipped,
                ],
            }

        return {"period_index": next_index}

    def route_after_advance(state: InvestigatorState) -> str:
        if state["period_index"] >= len(state["periods"]):
            return "synthesis"

        return "begin_period"

    # ------------------------------------------------------------------
    # Final synthesis
    # ------------------------------------------------------------------

    def synthesise(state: InvestigatorState) -> dict:
        evidence = _inspect_evidence(state["messages"])

        synthesis_input = {
            "research_question": state["question"],
            "research_plan": state["plan"],
            "period_summaries": state["period_summaries"],
            "inspected_passages": evidence,
        }

        messages = [
            SystemMessage(content=SYNTHESIS_PROMPT),
            HumanMessage(
                content=json.dumps(
                    synthesis_input,
                    ensure_ascii=False,
                    default=str,
                )
            ),
        ]

        try:
            request_budget.reserve(
                messages,
                max_output_tokens=INVESTIGATOR_MAX_OUTPUT_TOKENS,
            )

            started = time.monotonic()
            response = plain_llm.invoke(messages)

            logger.info(
                "Investigation synthesis received in %.2fs:\n%s",
                time.monotonic() - started,
                response.pretty_repr(),
            )

            return {"messages": [response]}

        except GroqTokenBudgetExceeded as exc:
            logger.warning(
                "Final synthesis exceeded the Groq token budget; "
                "returning the period summaries without model synthesis: %s",
                exc,
            )

            fallback = (
                "Final model synthesis was not available because the "
                "Groq request token budget was exceeded.\n\n"
                "The period summaries and inspected passage records "
                "below are retained as the investigation results.\n\n"
                + json.dumps(
                    {
                        "period_summaries": state["period_summaries"],
                        "inspected_passage_ids": [
                            item["passage_id"]
                            for item in evidence
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )

            return {
                "messages": [
                    AIMessage(content=fallback),
                ],
            }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route_after_period_model(state: InvestigatorState) -> str:
        last_message = state["period_messages"][-1]

        if not getattr(last_message, "tool_calls", []):
            return "summarise_period"

        if (
            state["tool_call_count"] >= state["max_tool_calls"]
            or state["period_tool_call_count"]
            >= state["max_period_tool_calls"]
        ):
            return "summarise_period"

        return "tools"

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    graph = StateGraph(InvestigatorState)

    graph.add_node("plan", plan)
    graph.add_node("begin_period", begin_period)
    graph.add_node("investigate_period", investigate_period)
    graph.add_node("tools", execute_period_tools)
    graph.add_node("summarise_period", summarise_period)
    graph.add_node("advance_period", advance_period)
    graph.add_node("synthesis", synthesise)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "begin_period")
    graph.add_edge("begin_period", "investigate_period")

    graph.add_conditional_edges(
        "investigate_period",
        route_after_period_model,
        {
            "tools": "tools",
            "summarise_period": "summarise_period",
        },
    )

    graph.add_edge("tools", "investigate_period")
    graph.add_edge("summarise_period", "advance_period")

    graph.add_conditional_edges(
        "advance_period",
        route_after_advance,
        {
            "begin_period": "begin_period",
            "synthesis": "synthesis",
        },
    )

    graph.add_edge("synthesis", END)

    return graph.compile(
        checkpointer=checkpointer or InMemorySaver()
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_investigation(
    question: str,
    *,
    llm: BaseChatModel | None = None,
    plain_llm: BaseChatModel | None = None,
    retriever: PassageRetriever | None = None,
    workflow: Any | None = None,
    start_year: int = 700,
    end_year: int = 1914,
    period_size: int = 100,
    max_tool_calls: int = 24,
    max_period_tool_calls: int = 4,
    thread_id: str | None = None,
) -> dict:
    if not question.strip():
        raise ValueError("question must not be empty")

    if not 1 <= max_tool_calls <= 100:
        raise ValueError("max_tool_calls must be between 1 and 100")

    if not 1 <= max_period_tool_calls <= max_tool_calls:
        raise ValueError(
            "max_period_tool_calls must be between 1 and max_tool_calls"
        )

    periods = make_periods(
        start_year=start_year,
        end_year=end_year,
        period_size=period_size,
    )

    if workflow is None:
        if retriever is None:
            raise ValueError(
                "A PassageRetriever is required when no workflow is supplied"
            )

        workflow = build_investigator_workflow(
            retriever,
            llm=llm,
            plain_llm=plain_llm,
            max_period_tool_calls=max_period_tool_calls,
        )

    initial_state: InvestigatorState = {
        "messages": [
            SystemMessage(
                content="You are conducting a historical corpus investigation."
            ),
            HumanMessage(content=question),
        ],
        "question": question,
        "plan": "",
        "periods": periods,
        "period_index": 0,
        "period_messages": [],
        "period_audit_messages": [],
        "period_summaries": [],
        "tool_call_count": 0,
        "period_tool_call_count": 0,
        "max_tool_calls": max_tool_calls,
        "max_period_tool_calls": max_period_tool_calls,
    }

    result = workflow.invoke(
        initial_state,
        config={
            "configurable": {
                "thread_id": thread_id or str(uuid4()),
            },
            "recursion_limit": (max_tool_calls * 2) + 20,
        },
    )

    record = build_investigation_record(result)

    record["research_question"] = question
    record["research_plan"] = result["plan"]
    record["periods"] = result["periods"]
    record["period_summaries"] = result["period_summaries"]

    result["investigation_record"] = record

    return result
