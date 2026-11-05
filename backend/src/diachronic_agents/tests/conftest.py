import pytest

from diachronic_agents.workflows.search_result import SearchResult


@pytest.fixture
def sample_search_result():
    """A small synthetic SearchResult for persistence tests."""

    return SearchResult(
        query="white hair",
        direction="reverse",
        initial_period=(1900, 2000),
        target_period=(1800, 1899),
        periods=[
            (1800, 1899),
            (1900, 2000),
        ],
        results={
            0: {
                "passages": [
                    {
                        "passage_id": "passage-001",
                        "text": "His hair was white as snow.",
                        "pub_year": 1850,
                    },
                ],
            },
            1: {
                "passages": [
                    {
                        "passage_id": "passage-002",
                        "text": "She had remarkably pale hair.",
                        "pub_year": 1920,
                    },
                ],
            },
        },
        graphs={
            0: {
                "nodes": [
                    {"id": "passage-001", "generation": 1},
                ],
                "edges": [],
            },
            1: {
                "nodes": [
                    {"id": "passage-002", "generation": 0},
                ],
                "edges": [],
            },
        },
        classifications={
            0: {
                "classifications": [
                    {
                        "passage_id": "passage-001",
                        "category": "human_hair",
                        "confidence": 0.95,
                    },
                ],
            },
            1: {
                "classifications": [
                    {
                        "passage_id": "passage-002",
                        "category": "human_hair",
                        "confidence": 0.88,
                    },
                ],
            },
        },
        prospects={
            0: [
                {
                    "passage_id": "passage-001",
                    "score": 0.91,
                },
            ],
            1: [
                {
                    "passage_id": "passage-002",
                    "score": 0.84,
                },
            ],
        },
        cumulative_graph={
            "metadata": {
                "search_count": 2,
                "node_count": 2,
                "edge_count": 1,
                "search_runs": [
                    {"search_id": "search-001"},
                    {"search_id": "search-002"},
                ],
            },
            "nodes": [
                {"id": "passage-001", "generation": 1},
                {"id": "passage-002", "generation": 0},
            ],
            "edges": [
                {
                    "id": "edge-001",
                    "source": "passage-002",
                    "target": "passage-001",
                },
            ],
            "seed_ids": ["passage-002"],
            "expanded_seed_ids": ["passage-002"],
            "unexpanded_seed_ids": [],
            "convergence": [],
        },
    )
