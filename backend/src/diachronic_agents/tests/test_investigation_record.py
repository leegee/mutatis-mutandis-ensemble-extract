# tests/test_investigation_record.py

import json

from langchain_core.messages import AIMessage, ToolMessage

from diachronic_agents.workflows.investigation_record import (
    build_investigation_record,
)


def test_builds_tool_call_trace_and_evidence():
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "semantic_search",
                "args": {
                    "query": "white hair",
                    "start_year": 1000,
                    "end_year": 1600,
                },
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    result = {
        "results": [
            {
                "passage_id": "p1",
                "pub_year": 1500,
                "title": "Example",
                "text": "An example passage.",
            }
        ],
        "warnings": ["One corpus partition was unavailable."],
    }

    tool_message = ToolMessage(
        content=json.dumps(result),
        name="semantic_search",
        tool_call_id="call_1",
    )

    record = build_investigation_record({
        "messages": [call, tool_message],
        "tool_call_count": 1,
    })

    assert record["schema_version"] == 1
    assert record["tool_call_count"] == 1

    assert record["tool_calls"][0]["tool_name"] == "semantic_search"
    assert record["tool_calls"][0]["status"] == "completed"
    assert record["tool_calls"][0]["result"] == result

    assert len(record["evidence"]) == 1

    evidence = record["evidence"][0]
    assert evidence["passage_id"] == "p1"
    assert evidence["observations"][0]["pub_year"] == 1500
    assert evidence["discovered_by"][0]["tool_call_id"] == "call_1"

    assert record["warnings"] == [
        {
            "tool_call_id": "call_1",
            "tool_name": "semantic_search",
            "warning": "One corpus partition was unavailable.",
        }
    ]


def test_deduplicates_passages_but_preserves_observations():
    search_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "semantic_search",
                "args": {"query": "white hair"},
                "id": "call_1",
                "type": "tool_call",
            },
            {
                "name": "inspect_passage",
                "args": {"passage_id": "p1"},
                "id": "call_2",
                "type": "tool_call",
            },
        ],
    )

    search_result = {
        "results": [
            {
                "passage_id": "p1",
                "pub_year": 1500,
                "text": "An example passage.",
            }
        ],
        "warnings": [],
    }

    inspection_result = {
        "passage_id": "p1",
        "pub_year": 1500,
        "text": "An example passage with more context.",
        "author": "Example Author",
    }

    messages = [
        search_call,
        ToolMessage(
            content=json.dumps(search_result),
            name="semantic_search",
            tool_call_id="call_1",
        ),
        ToolMessage(
            content=json.dumps(inspection_result),
            name="inspect_passage",
            tool_call_id="call_2",
        ),
    ]

    record = build_investigation_record({
        "messages": messages,
        "tool_call_count": 2,
    })

    assert len(record["evidence"]) == 1

    evidence = record["evidence"][0]
    assert len(evidence["observations"]) == 2
    assert {
        source["tool_name"]
        for source in evidence["discovered_by"]
    } == {"semantic_search", "inspect_passage"}


def test_preserves_unparseable_tool_content():
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_passage",
                "args": {"passage_id": "p1"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    record = build_investigation_record({
        "messages": [
            call,
            ToolMessage(
                content="Unexpected plain-text result",
                name="inspect_passage",
                tool_call_id="call_1",
            ),
        ],
        "tool_call_count": 1,
    })

    assert record["tool_calls"][0]["result"] == {
        "raw_content": "Unexpected plain-text result"
    }
    assert record["evidence"] == []


def test_records_tool_call_without_result():
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "semantic_search",
                "args": {"query": "white hair"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )

    record = build_investigation_record({
        "messages": [call],
        "tool_call_count": 0,
    })

    assert record["tool_calls"][0]["status"] == "not_returned"
    assert record["tool_calls"][0]["result"] is None
    