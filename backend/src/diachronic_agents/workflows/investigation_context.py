
from __future__ import annotations

import json
import re
from typing import Any, Sequence

from mutatis_mutandis.lib.corpus_logging import get_logger

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)


logger = get_logger(__name__)


DEFAULT_RECENT_ROUNDS = 1
DEFAULT_ACTIVE_SEARCH_RESULTS = 5
DEFAULT_MEMORY_ASSESSMENTS = 30
DEFAULT_MEMORY_QUESTIONS = 20
DEFAULT_MEMORY_SEARCHES = 20

LEDGER_MARKER_PATTERN = re.compile(
    r"<evidence_ledger_update>\s*(.*?)\s*</evidence_ledger_update>",
    re.DOTALL | re.IGNORECASE,
)

SEARCH_TOOLS = {
    "semantic_search",
    "search_from_passage",
    "lexical_search",
    "search_corpus",
}


def _decode_content(content: Any) -> Any:
    """Decode JSON tool output where possible."""

    if not isinstance(content, str):
        return content

    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"raw_content": content}


def _encode_content(content: Any) -> str:
    return json.dumps(
        content,
        ensure_ascii=False,
        default=str,
    )


def _message_text(message: BaseMessage) -> str:
    """Extract textual content from a message."""

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts)

    return ""


def _tool_result(message: ToolMessage) -> Any:
    return _decode_content(message.content)


def _passage_locator(
    passage: dict[str, Any],
    tool_name: str | None = None,
) -> dict[str, Any] | None:
    """Return the strongest available stable passage locator."""

    passage_id = passage.get("passage_id")

    if passage_id is not None:
        return {"passage_id": str(passage_id)}

    if tool_name == "lexical_search":
        doc_id = passage.get("doc_id")
        token_idx = passage.get("token_idx")

        if doc_id is not None and token_idx is not None:
            return {
                "doc_id": str(doc_id),
                "token_idx": int(token_idx),
            }

    return None


def _locator_key(locator: dict[str, Any]) -> str:
    if locator.get("passage_id") is not None:
        return f"passage:{locator['passage_id']}"

    return f"token:{locator['doc_id']}:{locator['token_idx']}"


def _compact_passage_metadata(
    passage: dict[str, Any],
    tool_name: str | None = None,
) -> dict[str, Any] | None:
    """Retain locator and bibliographic/search metadata, never passage text."""

    locator = _passage_locator(passage, tool_name)

    if locator is None:
        return None

    result: dict[str, Any] = {
        "locator": locator,
    }

    for field in (
        "corpus",
        "pub_year",
        "title",
        "author",
        "scale",
        "rank",
        "score",
        "sim_q",
        "sim_neg",
        "distance",
    ):
        value = passage.get(field)

        if value is not None:
            result[field] = value

    return result


def _is_search_result(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("results"), list)
    )


def _passages_from_payload(
    payload: Any,
) -> list[dict[str, Any]]:
    """Extract passage-shaped records from search or inspection output."""

    if not isinstance(payload, dict):
        return []

    results = payload.get("results")

    if isinstance(results, list):
        return [
            item
            for item in results
            if isinstance(item, dict)
        ]

    return [payload]


def _compact_search_payload(
    payload: dict[str, Any],
    *,
    tool_name: str,
    limit: int,
) -> dict[str, Any]:
    """Keep only a small, temporary set of locators from the latest search."""

    results = payload.get("results", [])
    compacted_results = []

    for passage in results[:limit]:
        if not isinstance(passage, dict):
            continue

        compacted = _compact_passage_metadata(
            passage,
            tool_name,
        )

        if compacted is not None:
            compacted_results.append(compacted)

    compacted: dict[str, Any] = {
        "results": compacted_results,
        "warnings": payload.get("warnings", []),
        "compacted": True,
        "text_omitted": True,
    }

    omitted = max(0, len(results) - len(compacted_results))

    if omitted:
        compacted["omitted_results"] = omitted

    return compacted


def _compact_inspection_payload(
    payload: Any,
    *,
    tool_name: str,
) -> dict[str, Any]:
    """Remove inspected passage text while preserving its locator and metadata."""

    if not isinstance(payload, dict):
        return {
            "compacted": True,
            "inspection_result": str(payload)[:500],
        }

    compacted = _compact_passage_metadata(payload, tool_name)

    if compacted is None:
        compacted = {}

    for field in ("warnings", "error"):
        if payload.get(field) is not None:
            compacted[field] = payload[field]

    compacted["compacted"] = True
    compacted["text_omitted"] = True

    return compacted


def _group_tool_rounds(
    messages: Sequence[BaseMessage],
) -> list[dict[str, Any]]:
    """Group each assistant tool-call message with its tool responses."""

    rounds: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            if current is not None:
                rounds.append(current)

            current = {
                "assistant": message,
                "tool_messages": [],
            }

        elif isinstance(message, ToolMessage) and current is not None:
            current["tool_messages"].append(message)

        elif current is not None:
            rounds.append(current)
            current = None

    if current is not None:
        rounds.append(current)

    return rounds


def _extract_ledger_updates(
    messages: Sequence[BaseMessage],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract explicit investigator assessments and questions from messages."""

    assessments: dict[str, dict[str, Any]] = {}
    questions: list[str] = []

    for message in messages:
        if not isinstance(message, AIMessage):
            continue

        content = _message_text(message)

        if not content:
            continue

        for match in LEDGER_MARKER_PATTERN.finditer(content):
            try:
                update = json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning(
                    "Could not decode evidence-ledger update in assistant message."
                )
                continue

            if not isinstance(update, dict):
                continue

            for assessment in update.get("assessments", []):
                if not isinstance(assessment, dict):
                    continue

                locator = assessment.get("locator")

                if not isinstance(locator, dict):
                    continue

                key = _locator_key(locator)

                # Require a supported, complete locator.
                if not (
                    locator.get("passage_id") is not None
                    or (
                        locator.get("doc_id") is not None
                        and locator.get("token_idx") is not None
                    )
                ):
                    continue

                cleaned: dict[str, Any] = {
                    "locator": locator,
                }

                for field in (
                    "pub_year",
                    "finding",
                    "interpretation",
                    "relevance",
                    "confidence",
                ):
                    value = assessment.get(field)

                    if value is not None:
                        cleaned[field] = value

                # Later assessments update earlier assessments for the same
                # passage, without losing fields omitted in the later update.
                previous = assessments.get(key, {})
                assessments[key] = {**previous, **cleaned}

            for question in update.get("outstanding_questions", []):
                if isinstance(question, str) and question.strip():
                    question = " ".join(question.split())

                    if question not in questions:
                        questions.append(question)

    return (
        list(assessments.values())[-DEFAULT_MEMORY_ASSESSMENTS:],
        questions[-DEFAULT_MEMORY_QUESTIONS:],
    )


def _summarise_older_rounds(
    rounds: Sequence[dict[str, Any]],
) -> str:
    """Build a bounded summary of older searches and inspections."""

    searches: list[str] = []
    inspected: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for round_data in rounds:
        assistant: AIMessage = round_data["assistant"]

        calls_by_id = {
            call.get("id"): call
            for call in assistant.tool_calls
        }

        for tool_message in round_data["tool_messages"]:
            call = calls_by_id.get(tool_message.tool_call_id, {})
            tool_name = (
                call.get("name")
                or tool_message.name
                or "unknown_tool"
            )
            arguments = call.get("args") or {}
            payload = _tool_result(tool_message)

            if isinstance(payload, dict):
                for warning in payload.get("warnings", []):
                    warnings.append(str(warning))

            if tool_name in SEARCH_TOOLS and _is_search_result(payload):
                query = (
                    arguments.get("query")
                    or arguments.get("passage_id")
                    or ""
                )

                start_year = arguments.get("start_year")
                end_year = arguments.get("end_year")

                period = (
                    f"{start_year}–{end_year}"
                    if start_year is not None and end_year is not None
                    else "unspecified period"
                )

                result_count = len(payload["results"])

                searches.append(
                    f"{tool_name}: {query!r}, {period}; "
                    f"{result_count} results."
                )

            elif tool_name == "inspect_passage":
                for passage in _passages_from_payload(payload):
                    compacted = _compact_passage_metadata(
                        passage,
                        tool_name,
                    )

                    if compacted is None:
                        continue

                    key = _locator_key(compacted["locator"])
                    inspected[key] = compacted

    sections = [
        "COMPACTED INVESTIGATION MEMORY",
        "This is a compact record of earlier activity. "
        "It contains no source excerpts. Use locators to revisit "
        "historical evidence when necessary.",
    ]

    if searches:
        sections.append("\nEarlier searches:")

        sections.extend(
            f"- {item}"
            for item in searches[-DEFAULT_MEMORY_SEARCHES:]
        )

    if inspected:
        sections.append("\nPreviously inspected passage references:")

        for key, passage in inspected.items():
            sections.append(
                f"- {key}: "
                f"{json.dumps(passage, ensure_ascii=False, default=str)}"
            )

    if warnings:
        sections.append("\nWarnings:")
        sections.extend(
            f"- {item}"
            for item in dict.fromkeys(warnings)
        )

    return "\n".join(sections)


def _compact_recent_tool_message(
    message: ToolMessage,
    *,
    tool_name: str,
) -> ToolMessage:
    """Compact every recent tool response; never retain passage text."""

    payload = _tool_result(message)

    if tool_name in SEARCH_TOOLS and _is_search_result(payload):
        compacted = _compact_search_payload(
            payload,
            tool_name=tool_name,
            limit=DEFAULT_ACTIVE_SEARCH_RESULTS,
        )

    elif tool_name == "inspect_passage":
        compacted = _compact_inspection_payload(
            payload,
            tool_name=tool_name,
        )

    else:
        # Preserve small non-passage tool responses. Truncate unusually
        # large responses so they cannot dominate the next model request.
        encoded = _encode_content(payload)

        if len(encoded) <= 2000:
            return message

        compacted = {
            "compacted": True,
            "original_length": len(encoded),
            "summary": encoded[:1500],
            "truncated": True,
        }

    return message.model_copy(
        update={"content": _encode_content(compacted)}
    )


def compact_investigation_context(
    messages: Sequence[BaseMessage],
    *,
    recent_rounds: int = DEFAULT_RECENT_ROUNDS,
) -> list[BaseMessage]:
    """Create compact working context without modifying the audit history.

    The original system prompt and research question are retained.
    Older tool rounds become a deterministic search/inspection history.
    Explicit evidence-ledger updates are retained without source excerpts.
    The most recent search round retains only a few locators for follow-up.
    All inspection results are stripped of passage text.
    """

    if len(messages) <= 2:
        return list(messages)

    prefix = list(messages[:2])
    rounds = _group_tool_rounds(messages[2:])

    if recent_rounds < 0:
        raise ValueError("recent_rounds cannot be negative")

    split_at = max(0, len(rounds) - recent_rounds)

    older_rounds = rounds[:split_at]
    recent_round_data = rounds[split_at:]

    compacted: list[BaseMessage] = list(prefix)

    if older_rounds:
        compacted.append(
            HumanMessage(
                content=_summarise_older_rounds(older_rounds),
                name="investigation_memory",
            )
        )

    assessments, questions = _extract_ledger_updates(messages)

    if assessments or questions:
        ledger = {
            "evidence_assessments": assessments,
            "outstanding_questions": questions,
        }

        compacted.append(
            HumanMessage(
                content=(
                    "PERSISTENT EVIDENCE LEDGER\n"
                    "These are investigator assessments, not source text. "
                    "Do not treat interpretations as established facts. "
                    "Use the locators to revisit source passages when needed.\n"
                    + _encode_content(ledger)
                ),
                name="evidence_ledger",
            )
        )

    for round_data in recent_round_data:
        assistant: AIMessage = round_data["assistant"]
        compacted.append(assistant)

        calls_by_id = {
            call.get("id"): call
            for call in assistant.tool_calls
        }

        for tool_message in round_data["tool_messages"]:
            call = calls_by_id.get(tool_message.tool_call_id, {})
            tool_name = (
                call.get("name")
                or tool_message.name
                or "unknown_tool"
            )

            compacted.append(
                _compact_recent_tool_message(
                    tool_message,
                    tool_name=tool_name,
                )
            )

    return compacted
