# pytest tests/test_search_result_store.py -v

import json

from diachronic_agents.workflows.diachronic_task import SearchResult
from diachronic_agents.persistence.search_result_store import (
    save_search_result,
    load_search_result,
)


def test_search_result_round_trip(tmp_path):
    original = SearchResult(
        query="white hair",
        direction="reverse",
        initial_period=(1900, 2000),
        target_period=(1500, 1899),
        periods=[(1850, 1899), (1800, 1849)],
        results={
            0: {"passages": [], "edges": []},
            1: {"passages": [], "edges": []},
        },
        graphs={
            0: {"nodes": [], "edges": []},
            1: {"nodes": [], "edges": []},
        },
        classifications={
            0: {
                "classifications": [
                    {
                        "passage_id": "P001",
                        "classification": "relevant",
                        "feature_type": "human_hair",
                        "reason": "White hair described",
                    }
                ]
            }
        },
        prospects={0: [], 1: []},
        cumulative_graph={
            "nodes": [{"id": "P001", "pub_year": 1850}],
            "edges": [],
            "convergence": [],
            "metadata": {"query": "white hair"},
        },
    )

    path = tmp_path / "search_result.json"

    save_search_result(original, path)
    loaded = load_search_result(path)

    assert loaded.query == original.query
    assert loaded.direction == original.direction
    assert loaded.initial_period == original.initial_period
    assert loaded.target_period == original.target_period
    assert loaded.periods == original.periods
    assert loaded.results == original.results
    assert loaded.graphs == original.graphs
    assert loaded.classifications == original.classifications
    assert loaded.prospects == original.prospects
    assert loaded.cumulative_graph == original.cumulative_graph

    # Also verify that the archive is valid, readable JSON.
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    assert data["schema_version"] == 1

