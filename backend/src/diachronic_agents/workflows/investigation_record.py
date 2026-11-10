from __future__ import annotations

import json
from typing import Any


SEARCH_TOOLS = {
    "semantic_search",
    "search_corpus",
    "search_from_passage",
    "lexical_search",
}



def _passage_locator(passage: dict[str, Any]) -> dict[str, Any] | None:
    """Return the strongest available stable locator for a passage."""

    passage_id = passage.get("passage_id")
    if passage_id is not None:
        return {"passage_id": str(passage_id)}

    doc_id = passage.get("doc_id")
    token_idx = passage.get("token_idx")

    if doc_id is not None and token_idx is not None:
        return {
            "doc_id": str(doc_id),
            "token_idx": int(token_idx),
        }

    return None


def _locator_key(locator: dict[str, Any]) -> str:
    """Create a deterministic key for either supported locator form."""

    if locator.get("passage_id") is not None:
        return f"passage:{locator['passage_id']}"

    return f"token:{locator['doc_id']}:{locator['token_idx']}"


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
    """Extract records with either supported passage locator."""

    if not isinstance(result, dict):
        return []

    passages = result.get("results")

    if isinstance(passages, list):
        candidates = passages
    else:
        candidates = [result]

    return [
        passage
        for passage in candidates
        if isinstance(passage, dict)
        and _passage_locator(passage) is not None
    ]


def _passage_locator(
    passage: dict[str, Any],
    tool_name: str | None = None,
) -> dict[str, Any] | None:
    """Return the strongest available stable locator."""

    passage_id = passage.get("passage_id")

    if passage_id is not None:
        return {"passage_id": str(passage_id)}

    # Lexical search results can be located within their source document.
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


def build_investigation_record(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a JSON-serialisable record of tool activity and passage evidence.

    `tool_calls` retains the complete original tool results for audit.
    The derived evidence indexes contain locators and provenance only.
    """

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

            for passage in _passages_from_result(result):
                locator = _passage_locator(passage, tool_name)

                if locator is None:
                    continue

                key = _locator_key(locator)

                item = evidence.setdefault(
                    key,
                    {
                        "locator": locator,
                        "pub_year": passage.get("pub_year"),
                        "title": passage.get("title"),
                        "observations": [],
                        "discovered_by": [],
                    },
                )

                if item.get("pub_year") is None:
                    item["pub_year"] = passage.get("pub_year")

                if item.get("title") is None:
                    item["title"] = passage.get("title")
                    
                # Preserve useful metadata without copying passage text.
                observation = {
                    "pub_year": passage.get("pub_year"),
                    "rank": passage.get("rank"),
                    "score": passage.get("score"),
                    "distance": passage.get("distance"),
                }

                if observation not in item["observations"]:
                    item["observations"].append(observation)

                source = {
                    "tool_call_id": call_id,
                    "tool_name": tool_name,
                    "arguments": call.get("args", {}),
                }

                if source not in item["discovered_by"]:
                    item["discovered_by"].append(source)

                if tool_name in SEARCH_TOOLS:
                    search_candidates.setdefault(key, item)

                elif tool_name == "inspect_passage":
                    inspected_passages.setdefault(key, item)

    return {
        "schema_version": 3,
        "tool_call_count": tool_call_count,
        "tool_calls": tool_calls,
        "search_candidates": list(search_candidates.values()),
        "inspected_passages": list(inspected_passages.values()),
        "evidence": list(evidence.values()),
        "warnings": warnings,
    }
    
