# pytest src/diachronic_agents/tests/test_search_result_integration.py -v -s

from diachronic_agents.workflows.diachronic_task import (
    run_diachronic_search,
)
from diachronic_agents.persistence.search_result_store import (
    save_search_result,
    load_search_result,
)


def test_real_search_result_round_trip(tmp_path):
    # Run a real diachronic search.
    original = run_diachronic_search(
        query="white hair",
        initial_period=(1900, 2000),
        target_period=(1800, 1899),
        period_size=100,
        direction="reverse",

        # Keep the experiment relatively small.
        initial_limit=5,
        seed_limit=2,
        transfer_limit=3,
        expansion_seed_count=2,
        prospect_limit=5,

        log_report=False,
    )

    assert original.results
    assert original.graphs
    assert original.cumulative_graph

    # Persist and reload the actual result.
    path = tmp_path / "real_search_result.json"

    save_search_result(original, path)
    restored = load_search_result(path)

    # Check the top-level metadata.
    assert restored.query == original.query
    assert restored.direction == original.direction
    assert restored.initial_period == original.initial_period
    assert restored.target_period == original.target_period
    assert restored.periods == original.periods

    # Check the actual retrieval data.
    assert restored.results == original.results
    assert restored.graphs == original.graphs

    # Check classifications and selected prospects.
    assert restored.prospects == original.prospects

    # Check the complete merged retrieval graph.
    assert restored.cumulative_graph == original.cumulative_graph

    # Classifications are restored as dictionaries.
    assert restored.classifications.keys() == original.classifications.keys()

    # Check that the search produced real retrieval data.
    assert any(
        result.get("passages")
        for result in original.results.values()
    )

    assert any(
        graph.get("nodes")
        for graph in original.graphs.values()
    )

    assert original.cumulative_graph["metadata"]["search_count"] >= 1

    # Check that classifications survived serialisation.
    assert restored.classifications.keys() == original.classifications.keys()

    for period_index, classification in restored.classifications.items():
        assert isinstance(classification, dict)
        assert "classifications" in classification


def test_multi_period_search_result_round_trip(tmp_path):
    original = run_diachronic_search(
        query="white hair",
        initial_period=(1900, 2000),
        target_period=(1700, 1899),
        period_size=100,
        direction="reverse",
        initial_limit=5,
        seed_limit=2,
        transfer_limit=3,
        expansion_seed_count=2,
        prospect_limit=5,
        log_report=False,
    )

    # Confirm that the search actually covered multiple periods.
    assert len(original.graphs) >= 2
    assert len(original.results) >= 2

    # Confirm that search-run metadata accumulated across periods.
    metadata = original.cumulative_graph["metadata"]
    search_runs = metadata["search_runs"]

    assert metadata["search_count"] == len(search_runs)
    assert metadata["search_count"] >= 2

    search_ids = [
        run["search_id"]
        for run in search_runs
    ]

    assert len(search_ids) == len(set(search_ids))

    # Confirm that the cumulative graph contains the merged data.
    assert metadata["node_count"] == len(
        original.cumulative_graph["nodes"]
    )
    assert metadata["edge_count"] == len(
        original.cumulative_graph["edges"]
    )

    # Save and reload the complete result.
    path = tmp_path / "multi_period_search_result.json"

    save_search_result(original, path)
    restored = load_search_result(path)

    # Verify the complete round trip.
    assert restored.to_dict() == original.to_dict()
    