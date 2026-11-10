# workflows/investigation_record.py

from __future__ import annotations

import json
from typing import Any


def _decode_tool_result(content: Any) -> Any:
    """Decode a tool message's content without discarding unparseable data."""

    if isinstance(content, (dict, list)):
        return content

    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw_content": content}

    return {"raw_content": str(content)}


def _passages_from_result(result: Any) -> list[dict[str, Any]]:
    """Extract passage records from search or inspection tool results."""

    if not isinstance(result, dict):
        return []

    passages = result.get("results")

    if isinstance(passages, list):
        return [
            passage
            for passage in passages
            if isinstance(passage, dict)
            and passage.get("passage_id") is not None
        ]

    if result.get("passage_id") is not None:
        return [result]

    return []


def build_investigation_record(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Build a JSON-serialisable record of tool activity and passage evidence."""

    messages = state.get("messages", [])
    tool_call_count = state.get("tool_call_count", 0)

    tool_messages = {
        getattr(message, "tool_call_id", None): message
        for message in messages
        if getattr(message, "tool_call_id", None) is not None
    }

    tool_calls: list[dict[str, Any]] = []
    evidence: dict[str, dict[str, Any]] = {}
    search_candidates: dict[str, dict[str, Any]] = {}
    inspected_passages: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []

    for message in messages:
        for call in getattr(message, "tool_calls", []):
            call_id = call.get("id")
            tool_name = call.get("name")
            tool_message = tool_messages.get(call_id)

            result = (
                _decode_tool_result(tool_message.content)
                if tool_message is not None
                else None
            )

            is_error = (
                getattr(tool_message, "status", None) == "error"
                if tool_message is not None
                else False
            )

            entry = {
                "tool_call_id": call_id,
                "tool_name": tool_name,
                "arguments": call.get("args", {}),
                "result": result,
                "status": (
                    "not_returned"
                    if tool_message is None
                    else "error" if is_error else "completed"
                ),
            }
            tool_calls.append(entry)

            if tool_message is None or is_error:
                continue

            if isinstance(result, dict):
                for warning in result.get("warnings", []):
                    warnings.append({
                        "tool_call_id": call_id,
                        "tool_name": tool_name,
                        "warning": warning,
                    })

            passages = _passages_from_result(result)

            for passage in passages:
                passage_id = str(passage["passage_id"])

                item = evidence.setdefault(
                    passage_id,
                    {
                        "passage_id": passage_id,
                        "observations": [],
                        "discovered_by": [],
                    },
                )

                if passage not in item["observations"]:
                    item["observations"].append(passage)

                source = {
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "arguments": call.get("args", {}),
                }

                if source not in item["discovered_by"]:
                    item["discovered_by"].append(source)

                # Keep search candidates and inspected passages distinct.
                if tool_name in {"semantic_search", "search_corpus"}:
                    search_candidates.setdefault(passage_id, item)

                elif tool_name == "inspect_passage":
                    inspected_passages.setdefault(passage_id, item)

    return {
        "schema_version": 2,
        "tool_call_count": tool_call_count,
        "tool_calls": tool_calls,
        "search_candidates": list(search_candidates.values()),
        "inspected_passages": list(inspected_passages.values()),
        "evidence": list(evidence.values()),  # Retained for compatibility.
        "warnings": warnings,
    }
    