# workflows/investigation_context.py


from __future__ import annotations

import json
from typing import Any, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)


DEFAULT_RECENT_ROUNDS = 2
DEFAULT_SEARCH_RESULTS = 5
DEFAULT_SEARCH_EXCERPT_CHARS = 250
DEFAULT_MEMORY_RESULTS = 15
DEFAULT_MEMORY_EXCERPT_CHARS = 180
DEFAULT_INSPECTION_EXCERPT_CHARS = 400


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


def _excerpt(value: Any, limit: int) -> str | None:
    if value is None:
        return None

    text = " ".join(str(value).split())

    if len(text) > limit:
        return text[:limit].rstrip() + "…"

    return text


def _compact_passage(
    passage: dict[str, Any],
    *,
    excerpt_chars: int,
) -> dict[str, Any]:
    """Keep useful evidence metadata and a short text excerpt."""

    fields = (
        "passage_id",
        "corpus",
        "doc_id",
        "pub_year",
        "title",
        "author",
        "scale",
        "rank",
        "score",
        "sim_q",
        "sim_neg",
        "distance",
    )

    result = {
        key: passage[key]
        for key in fields
        if passage.get(key) is not None
    }

    excerpt = _excerpt(passage.get("text"), excerpt_chars)

    if excerpt:
        result["excerpt"] = excerpt

    return result


def _tool_result(message: ToolMessage) -> Any:
    return _decode_content(message.content)


def _is_search_result(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("results"), list)
    )


def _compact_search_payload(
    payload: dict[str, Any],
    *,
    limit: int,
    excerpt_chars: int,
) -> dict[str, Any]:
    results = payload.get("results", [])

    compacted = {
        "results": [
            _compact_passage(
                result,
                excerpt_chars=excerpt_chars,
            )
            for result in results[:limit]
            if isinstance(result, dict)
        ],
        "warnings": payload.get("warnings", []),
        "compacted": True,
    }

    omitted = max(0, len(results) - limit)

    if omitted:
        compacted["omitted_results"] = omitted

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


def _summarise_older_rounds(
    rounds: Sequence[dict[str, Any]],
) -> str:
    """Build a bounded, deterministic summary of older tool activity."""

    searches: list[str] = []
    candidates: dict[str, dict[str, Any]] = {}
    inspections: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    observations: list[str] = []

    for round_data in rounds:
        assistant: AIMessage = round_data["assistant"]

        calls_by_id = {
            call.get("id"): call
            for call in assistant.tool_calls
        }

        if isinstance(assistant.content, str) and assistant.content.strip():
            observations.append(
                _excerpt(assistant.content, 400) or ""
            )

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

            if _is_search_result(payload):
                results = payload["results"]

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

                searches.append(
                    f"{tool_name}: {query!r}, {period}; "
                    f"{len(results)} results."
                )

                for passage in results[:3]:
                    if not isinstance(passage, dict):
                        continue

                    passage_id = passage.get("passage_id")

                    if passage_id is None:
                        continue

                    candidates[str(passage_id)] = _compact_passage(
                        passage,
                        excerpt_chars=DEFAULT_MEMORY_EXCERPT_CHARS,
                    )

            elif (
                isinstance(payload, dict)
                and payload.get("passage_id") is not None
            ):
                passage_id = str(payload["passage_id"])

                inspections[passage_id] = _compact_passage(
                    payload,
                    excerpt_chars=DEFAULT_INSPECTION_EXCERPT_CHARS,
                )

    sections = [
        "COMPACTED INVESTIGATION MEMORY",
        "The following records summarise earlier tool activity. "
        "They are leads and evidence references, not independent "
        "historical conclusions. Full results remain in the audit record.",
    ]

    if searches:
        sections.append("\nEarlier searches:")
        sections.extend(f"- {item}" for item in searches)

    if candidates:
        sections.append("\nEarlier search candidates:")

        for passage_id, passage in list(candidates.items())[
            -DEFAULT_MEMORY_RESULTS:
        ]:
            sections.append(
                f"- {passage_id}: "
                f"{json.dumps(passage, ensure_ascii=False, default=str)}"
            )

    if inspections:
        sections.append("\nEarlier inspected passages:")

        for passage_id, passage in inspections.items():
            sections.append(
                f"- {passage_id}: "
                f"{json.dumps(passage, ensure_ascii=False, default=str)}"
            )

    if observations:
        sections.append("\nEarlier investigator observations:")
        sections.extend(f"- {item}" for item in observations[-8:])

    if warnings:
        sections.append("\nWarnings:")
        sections.extend(f"- {item}" for item in dict.fromkeys(warnings))

    return "\n".join(sections)


def _compact_recent_tool_message(
    message: ToolMessage,
    *,
    full_inspection: bool,
) -> ToolMessage:
    """Compact search output while retaining recent inspection evidence."""

    if full_inspection:
        return message

    payload = _tool_result(message)

    if _is_search_result(payload):
        compacted = _compact_search_payload(
            payload,
            limit=DEFAULT_SEARCH_RESULTS,
            excerpt_chars=DEFAULT_SEARCH_EXCERPT_CHARS,
        )

        return message.model_copy(
            update={"content": _encode_content(compacted)}
        )

    # Keep other recent tool results unless they are unusually large.
    encoded = _encode_content(payload)

    if len(encoded) > 8000:
        encoded = encoded[:8000] + "\n[Tool output truncated in working context.]"

        return message.model_copy(
            update={"content": encoded}
        )

    return message


def compact_investigation_context(
    messages: Sequence[BaseMessage],
    *,
    recent_rounds: int = DEFAULT_RECENT_ROUNDS,
) -> list[BaseMessage]:
    """Create a compact LLM context without modifying the audit history.

    The original system prompt and research question are retained.
    Older tool rounds become a deterministic evidence summary.
    Recent tool-call rounds retain their call/response structure.
    """

    if len(messages) <= 2:
        return list(messages)

    rounds = _group_tool_rounds(messages[2:])

    if not rounds:
        return list(messages)

    prefix = list(messages[:2])

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

    # Retain full text for the three most recent inspections.
    inspection_messages = []

    for round_data in reversed(recent_round_data):
        for tool_message in reversed(round_data["tool_messages"]):
            if tool_message.name == "inspect_passage":
                inspection_messages.append(tool_message)

            if len(inspection_messages) >= 3:
                break

        if len(inspection_messages) >= 3:
            break

    full_inspection_ids = {
        id(message)
        for message in inspection_messages
    }

    for round_data in recent_round_data:
        compacted.append(round_data["assistant"])

        for tool_message in round_data["tool_messages"]:
            compacted.append(
                _compact_recent_tool_message(
                    tool_message,
                    full_inspection=id(tool_message) in full_inspection_ids,
                )
            )

    return compacted

