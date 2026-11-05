# pytest tests/test_search_result_store.py -v

import json
from pathlib import Path

from diachronic_agents.workflows.search_result import SearchResult
from diachronic_agents.persistence.search_result_store import (
    save_search_result,
    load_search_result,
    get_search_result_summary,
    list_search_results,
)

Karikó Katalin 
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


def test_search_result_summary(
    tmp_path,
    sample_search_result,
):
    path = tmp_path / "search.json"

    save_search_result(sample_search_result, path)

    summary = get_search_result_summary(path)

    assert summary["filename"] == "search.json"
    assert summary["query"] == "white hair"
    assert summary["direction"] == "reverse"
    assert summary["initial_period"] == [1900, 2000]
    assert summary["target_period"] == [1800, 1899]

    assert summary["period_count"] == 2
    assert summary["result_period_count"] == 2
    assert summary["graph_period_count"] == 2
    assert summary["passage_count"] == 2
    assert summary["classification_period_count"] == 2
    assert summary["prospect_period_count"] == 2

    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["search_count"] == 2

    assert summary["size_bytes"] > 0
    assert summary["saved_at"]


def test_list_search_results(
    tmp_path,
    sample_search_result,
):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    first_path = archive_dir / "first.json"
    second_path = archive_dir / "second.json"

    save_search_result(sample_search_result, first_path)
    save_search_result(sample_search_result, second_path)

    summaries = list_search_results(archive_dir)

    assert len(summaries) == 2

    filenames = {
        summary["filename"]
        for summary in summaries
    }

    assert filenames == {
        "first.json",
        "second.json",
    }


def test_list_search_results_missing_directory(tmp_path):
    summaries = list_search_results(
        tmp_path / "does_not_exist"
    )

    assert summaries == []


def test_list_search_results_skips_invalid_archives(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    invalid_path = archive_dir / "broken.json"
    invalid_path.write_text(
        "{ invalid json",
        encoding="utf-8",
    )

    summaries = list_search_results(archive_dir)

    assert summaries == []

