# tests/test_investigator.py

from __future__ import annotations

import pytest

from langchain_core.messages import AIMessage

from diachronic_agents.workflows.investigator import (
    build_investigator_workflow,
    run_investigation,
)
from diachronic_agents.llm.request_budget import GroqRequestBudget

class FakePassageRetriever:
    def __init__(self):
        self.calls = []

    def search_text(self, query, **kwargs):
        self.calls.append(("search_text", query, kwargs))
        return {
            "results": [
                {
                    "passage_id": "p1",
                    "pub_year": 1500,
                    "title": "Example",
                    "text": "An example passage.",
                }
            ],
            "warnings": [],
        }

    def search_from_passage(self, passage_id, **kwargs):
        self.calls.append(("search_from_passage", passage_id, kwargs))
        return {"results": [], "warnings": []}

    def search_lexical(self, query, **kwargs):
        self.calls.append(("search_lexical", query, kwargs))
        return {"results": [], "warnings": []}

    def inspect_passage(self, passage_id, **kwargs):
        self.calls.append(("inspect_passage", passage_id, kwargs))
        return {"passage_id": passage_id, "text": "An example passage."}


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


def tool_call(name, args, call_id="call_1"):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def test_investigator_can_finish_without_tools():
    retriever = FakePassageRetriever()
    llm = FakeLLM([
        AIMessage(content="There is insufficient evidence to answer.")
    ])

    workflow = build_investigator_workflow(retriever, llm=llm, request_budget=GroqRequestBudget(tpm_limit=7600),)

    result = run_investigation(
        "Investigate the representation of white hair.",
        workflow=workflow,
    )

    assert result["tool_call_count"] == 0
    assert result["messages"][-1].content == (
        "There is insufficient evidence to answer."
    )
    assert retriever.calls == []


def test_investigator_executes_tool_and_continues():
    retriever = FakePassageRetriever()
    llm = FakeLLM([
        tool_call(
            "semantic_search",
            {
                "query": "white hair",
                "start_year": 1000,
                "end_year": 1600,
                "limit": 5,
            },
        ),
        AIMessage(content="The search found one relevant passage."),
    ])

    workflow = build_investigator_workflow(retriever, llm=llm, request_budget=GroqRequestBudget(tpm_limit=7600),)

    result = run_investigation(
        "Investigate the representation of white hair.",
        workflow=workflow,
        max_tool_calls=3,
    )

    assert result["tool_call_count"] == 1
    assert result["messages"][-1].content == (
        "The search found one relevant passage."
    )
    assert retriever.calls[0][0] == "search_text"

    # The investigation record is generated automatically.
    record = result["investigation_record"]

    assert record["schema_version"] == 1
    assert record["tool_call_count"] == 1

    # The tool call and its result are preserved.
    assert len(record["tool_calls"]) == 1
    assert record["tool_calls"][0]["tool_name"] == "semantic_search"
    assert record["tool_calls"][0]["status"] == "completed"

    # The passage returned by the search appears in the evidence ledger.
    assert len(record["evidence"]) == 1

    evidence = record["evidence"][0]
    assert evidence["passage_id"] == "p1"
    assert evidence["observations"][0]["pub_year"] == 1500
    assert evidence["discovered_by"][0]["tool_name"] == "semantic_search"


def test_investigator_stops_at_tool_call_budget():
    retriever = FakePassageRetriever()
    llm = FakeLLM([
        tool_call(
            "semantic_search",
            {
                "query": "white hair",
                "start_year": 1000,
                "end_year": 1600,
                "limit": 5,
            },
            "call_1",
        ),
        tool_call(
            "lexical_search",
            {
                "query": "white hair",
                "start_year": 1000,
                "end_year": 1600,
                "limit": 5,
            },
            "call_2",
        ),
        AIMessage(content="Summary based on the evidence gathered."),
    ])

    workflow = build_investigator_workflow(retriever, llm=llm, request_budget=GroqRequestBudget(tpm_limit=20_000),)

    result = run_investigation(
        "Investigate the representation of white hair.",
        workflow=workflow,
        max_tool_calls=1,
    )

    assert result["tool_call_count"] == 1
    assert [call[0] for call in retriever.calls] == ["search_text"]
    assert result["messages"][-1].content == (
        "Summary based on the evidence gathered."
    )


@pytest.mark.parametrize(
    ("question", "max_tool_calls"),
    [
        ("", 5),
        ("   ", 5),
        ("A research question", 0),
        ("A research question", 101),
    ],
)
def test_rejects_invalid_run_arguments(question, max_tool_calls):
    with pytest.raises(ValueError):
        run_investigation(
            question,
            retriever=FakePassageRetriever(),
            max_tool_calls=max_tool_calls,
        )


def test_investigation_record_exists_without_tool_calls():
    retriever = FakePassageRetriever()
    llm = FakeLLM([
        AIMessage(content="There is insufficient evidence to answer.")
    ])

    workflow = build_investigator_workflow(retriever, llm=llm, request_budget=GroqRequestBudget(tpm_limit=7600),)

    result = run_investigation(
        "Investigate the representation of white hair.",
        workflow=workflow,
    )

    record = result["investigation_record"]

    assert record["tool_call_count"] == 0
    assert record["tool_calls"] == []
    assert record["evidence"] == []
    assert record["warnings"] == []

