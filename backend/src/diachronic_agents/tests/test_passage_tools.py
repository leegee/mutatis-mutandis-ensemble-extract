# tests/test_passage_tools.py

from __future__ import annotations

import pytest

from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.tools.passage_tools import build_passage_tools


class FakePassageRetriever:
    def __init__(self):
        self.calls = []

    def search_text(self, query, **kwargs):
        self.calls.append(("search_text", query, kwargs))
        return {"results": [], "warnings": []}

    def search_from_passage(self, passage_id, **kwargs):
        self.calls.append(("search_from_passage", passage_id, kwargs))
        return {"results": [], "warnings": []}

    def search_lexical(self, query, **kwargs):
        self.calls.append(("search_lexical", query, kwargs))
        return {"results": [], "warnings": []}

    def inspect_passage(self, passage_id, **kwargs):
        self.calls.append(("inspect_passage", passage_id, kwargs))
        return {"passage_id": passage_id, "text": "Example passage"}


@pytest.fixture
def retriever():
    return FakePassageRetriever()


@pytest.fixture
def tools(retriever):
    return {
        tool.name: tool
        for tool in build_passage_tools(retriever)
    }


def test_builds_expected_tools(tools):
    assert set(tools) == {
        "semantic_search",
        "search_from_passage",
        "lexical_search",
        "inspect_passage",
    }


def test_semantic_search_forwards_arguments(tools, retriever):
    result = tools["semantic_search"].invoke({
        "query": "white hair",
        "start_year": 1000,
        "end_year": 1500,
        "representation": "l8",
        "scale": "broad",
        "limit": 5,
        "include_text": True,
    })

    assert result == {"results": [], "warnings": []}
    assert retriever.calls == [
        (
            "search_text",
            "white hair",
            {
                "representation": "l8",
                "start_year": 1000,
                "end_year": 1500,
                "limit": 5,
                "scale": "broad",
                "include_text": True,
            },
        )
    ]


def test_search_from_passage_forwards_arguments(tools, retriever):
    tools["search_from_passage"].invoke({
        "passage_id": "passage-123",
        "start_year": 1500,
        "end_year": 1700,
        "representation": "mean4",
        "limit": 8,
    })

    assert retriever.calls == [
        (
            "search_from_passage",
            "passage-123",
            {
                "representation": "mean4",
                "start_year": 1500,
                "end_year": 1700,
                "limit": 8,
                "scale": None,
                "include_text": True,
            },
        )
    ]


def test_lexical_search_forwards_arguments(tools, retriever):
    tools["lexical_search"].invoke({
        "query": "white hair",
        "start_year": 1600,
        "end_year": 1700,
        "limit": 12,
        "window_tokens": 60,
    })

    assert retriever.calls == [
        (
            "search_lexical",
            "white hair",
            {
                "start_year": 1600,
                "end_year": 1700,
                "limit": 12,
                "window_tokens": 60,
            },
        )
    ]


def test_inspect_passage_forwards_arguments(tools, retriever):
    result = tools["inspect_passage"].invoke({
        "passage_id": "passage-456",
        "representation": "last",
    })

    assert result == {
        "passage_id": "passage-456",
        "text": "Example passage",
    }
    assert retriever.calls == [
        (
            "inspect_passage",
            "passage-456",
            {
                "representation": "last",
                "max_chars": 1200,
            },
        )
    ]

@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        (
            "semantic_search",
            {"query": "test", "start_year": 1500, "end_year": 1400},
        ),
        (
            "search_from_passage",
            {"passage_id": "p1", "start_year": 1500, "end_year": 1400},
        ),
        (
            "lexical_search",
            {"query": "test", "start_year": 1500, "end_year": 1400},
        ),
    ],
)
def test_rejects_reversed_year_range(tools, tool_name, arguments):
    with pytest.raises(ValueError, match="start_year"):
        tools[tool_name].invoke(arguments)


@pytest.mark.parametrize("limit", [0, 21, -1])
def test_rejects_invalid_result_limit(tools, limit):
    with pytest.raises(ValueError, match="limit"):
        tools["semantic_search"].invoke({
            "query": "test",
            "start_year": 1500,
            "end_year": 1600,
            "limit": limit,
        })


def test_rejects_invalid_lexical_window(tools):
    with pytest.raises(ValueError, match="window_tokens"):
        tools["lexical_search"].invoke({
            "query": "test",
            "start_year": 1500,
            "end_year": 1600,
            "window_tokens": 0,
        })


def test_tools_are_bound_to_injected_retriever(tools, retriever):
    assert len(tools) == 4
    tools["inspect_passage"].invoke({"passage_id": "p1"})
    assert retriever.calls[0][0] == "inspect_passage"

    