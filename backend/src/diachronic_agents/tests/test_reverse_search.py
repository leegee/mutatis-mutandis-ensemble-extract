"""
diachronic_agents/tests/test_reverse_search.py

    uv run pytest src/diachronic_agents/tests -q
"""

from langgraph.checkpoint.memory import InMemorySaver

from diachronic_agents.workflows.reverse_search import (
    build_reverse_search_workflow,
)


class FakeRetriever:

    def search_text(self, **kwargs):
        return {
            "results": [
                {
                    "passage_id": "seed-a",
                    "pub_year": 1920,
                    "scale": "broad",
                    "rank": 1,
                    "score": 0.9,
                },
                {
                    "passage_id": "seed-b",
                    "pub_year": 1910,
                    "scale": "broad",
                    "rank": 2,
                    "score": 0.8,
                },
            ],
            "warnings": [],
        }

    def search_from_passage(self, passage_id, **kwargs):
        if passage_id == "seed-a":
            results = [
                {
                    "passage_id": "old-a",
                    "pub_year": 1880,
                    "scale": "broad",
                    "rank": 1,
                    "score": 0.85,
                },
                {
                    "passage_id": "shared",
                    "pub_year": 1870,
                    "scale": "broad",
                    "rank": 2,
                    "score": 0.75,
                },
            ]
        else:
            results = [
                {
                    "passage_id": "shared",
                    "pub_year": 1870,
                    "scale": "broad",
                    "rank": 1,
                    "score": 0.88,
                },
                {
                    "passage_id": "old-b",
                    "pub_year": 1860,
                    "scale": "broad",
                    "rank": 2,
                    "score": 0.7,
                },
            ]

        return {
            "results": results,
            "warnings": [],
        }


def test_reverse_search_preserves_multiple_edges():

    workflow = build_reverse_search_workflow(
        FakeRetriever(),
        checkpointer=InMemorySaver(),
    )

    result = workflow.invoke(
        {
            "query": "white hair",
            "initial_start_year": 1900,
            "initial_end_year": 1950,
            "reverse_start_year": 1850,
            "reverse_end_year": 1899,
            "representation": "l8",
            "initial_scale": "broad",
            "historical_scale": "broad",
            "initial_limit": 10,
            "seed_limit": 2,
            "transfer_limit": 5,
        },
        config={
            "configurable": {
                "thread_id": "test-reverse-search",
            }
        },
    )

    passage_ids = {
        passage["passage_id"]
        for passage in result["passages"]
    }

    assert passage_ids == {
        "seed-a",
        "seed-b",
        "old-a",
        "shared",
        "old-b",
    }

    shared_edges = [
        edge for edge in result["edges"]
        if edge["target_passage_id"] == "shared"
    ]

    assert len(shared_edges) == 2

    assert {
        edge["source_passage_id"]
        for edge in shared_edges
    } == {"seed-a", "seed-b"}

