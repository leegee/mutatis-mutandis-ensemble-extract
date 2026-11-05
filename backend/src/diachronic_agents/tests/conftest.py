import pytest

from diachronic_agents.workflows.search_result import SearchResult


def make_node(
    passage_id: str,
    pub_year: int,
    generation: int,
    *,
    is_seed: bool = False,
    was_expanded: bool = False,
    seed_generations: list[int] | None = None,
    expanded_generations: list[int] | None = None,
) -> dict:
    return {
        "passage_id": passage_id,
        "corpus": "eebo",
        "doc_id": f"doc_{passage_id}",
        "pub_year": pub_year,
        "scale": "broad",
        "rank": 1,
        "distance": 0.05,
        "score": 0.95,
        "title": f"Test passage {passage_id}",
        "author": "Test Author",
        "text": f"Test passage text for {passage_id}.",
        "char_start": 0,
        "char_end": 100,
        "word_start": 0,
        "word_end": 20,
        "token_start": 0,
        "token_end": 20,
        "filepath": f"test/{passage_id}.txt",
        "id": passage_id,
        "generation": generation,
        "is_seed": is_seed,
        "was_expanded": was_expanded,
        "seed_generations": seed_generations or [],
        "expanded_generations": expanded_generations or [],
        "discovery_sources": (
            ["initial_search"] if generation == 0 else ["historical_search"]
        ),
        "classification": "relevant",
        "feature_type": "human_hair",
        "classification_reason": "Test classification",
    }


@pytest.fixture
def sample_search_result():
    """A small synthetic SearchResult for persistence tests."""

    cumulative_graph = {
        "metadata": {
            "search_count": 2,
            "node_count": 3,
            "edge_count": 2,
            "seed_count": 1,
            "expanded_seed_count": 1,
            "convergence_count": 0,
            "query": "white hair",
            "direction": "reverse",
            "search_runs": [
                {
                    "search_id": "search_0",
                    "search_direction": "reverse",
                    "generation": 0,
                    "representation": "l8",
                    "initial_period": [1900, 2000],
                    "target_period": [1800, 1899],
                    "seed_ids": ["passage-002"],
                },
                {
                    "search_id": "search_1",
                    "search_direction": "reverse",
                    "generation": 1,
                    "representation": "l8",
                    "initial_period": [1850, 1899],
                    "target_period": [1700, 1849],
                    "seed_ids": ["passage-001"],
                },
            ],
        },
        "nodes": [
            make_node(
                "passage-002",
                1920,
                0,
                is_seed=True,
                was_expanded=True,
                seed_generations=[0],
                expanded_generations=[0],
            ),
            make_node(
                "passage-001",
                1850,
                1,
                is_seed=True,
                was_expanded=True,
                seed_generations=[1],
                expanded_generations=[1],
            ),
            make_node(
                "passage-003",
                1750,
                1,
            ),
        ],
        "edges": [
            {
                "source_passage_id": "passage-002",
                "target_passage_id": "passage-001",
                "source_pub_year": 1920,
                "target_pub_year": 1850,
                "source_scale": "broad",
                "target_scale": "broad",
                "representation": "l8",
                "rank": 1,
                "distance": 0.05,
                "score": 0.95,
                "source_period": [1900, 2000],
                "target_period": [1800, 1899],
                "search_direction": "reverse",
                "source": "passage-002",
                "target": "passage-001",
                "search_id": "search_0",
                "generation": 0,
                "id": "edge_0",
            },
            {
                "source_passage_id": "passage-001",
                "target_passage_id": "passage-003",
                "source_pub_year": 1850,
                "target_pub_year": 1750,
                "source_scale": "broad",
                "target_scale": "broad",
                "representation": "l8",
                "rank": 1,
                "distance": 0.04,
                "score": 0.96,
                "source_period": [1850, 1899],
                "target_period": [1700, 1849],
                "search_direction": "reverse",
                "source": "passage-001",
                "target": "passage-003",
                "search_id": "search_1",
                "generation": 1,
                "id": "edge_1",
            },
        ],
        "seed_ids": ["passage-002", "passage-001"],
        "expanded_seed_ids": ["passage-002", "passage-001"],
        "unexpanded_seed_ids": [],
        "convergence": [],
    }

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

        cumulative_graph = cumulative_graph,        
    )
