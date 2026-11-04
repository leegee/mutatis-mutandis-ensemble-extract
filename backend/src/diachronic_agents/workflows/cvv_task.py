# workflows/csv_task.py

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from diachronic_agents.workflows.diachronic_task import SearchResult
from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_logging import get_logger


logger = get_logger(__name__)


def _write_csv(
    output_path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> Path:
    """Write a list of dictionaries to a CSV file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)

    return output_path


def create_csv(
    search_result: SearchResult,
    *,
    output_dir: str | Path | None = None,
    filename_prefix: str | None = None,
) -> tuple[Path, Path]:
    """
    Export the cumulative retrieval graph as nodes and edges CSV files.

    Returns:
        Tuple containing (nodes_csv_path, edges_csv_path).
    """

    if not isinstance(search_result, SearchResult):
        raise TypeError(
            "search_result must be a SearchResult instance"
        )

    retrieval_graph = search_result.cumulative_graph

    if not retrieval_graph:
        raise ValueError(
            "SearchResult contains no cumulative retrieval graph"
        )

    if output_dir is None:
        output_dir = OUT_DIR / "csv"

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename_prefix is None:
        filename_prefix = (
            f"{search_result.query.replace(' ', '_')}_"
            f"{search_result.direction}"
        )

    nodes = retrieval_graph.get("nodes", [])
    edges = retrieval_graph.get("edges", [])

    node_fields = [
        "id",
        "passage_id",
        "pub_year",
        "generation",
        "seed",
        "expanded",
        "classification",
        "feature_type",
        "classification_reason",
        "title",
        "text",
    ]

    edge_fields = [
        "source",
        "target",
        "generation",
        "source_period",
        "target_period",
        "source_passage_id",
        "target_passage_id",
        "source_pub_year",
        "target_pub_year",
        "search_direction",
        "representation",
        "scale",
        "rank",
        "distance",
        "score",
    ]

    nodes_path = output_dir / f"{filename_prefix}_nodes.csv"
    edges_path = output_dir / f"{filename_prefix}_edges.csv"

    nodes_path = _write_csv(
        nodes_path,
        nodes,
        node_fields,
    )

    edges_path = _write_csv(
        edges_path,
        edges,
        edge_fields,
    )

    logger.info(
        "CSV export complete | nodes=%d | edges=%d",
        len(nodes),
        len(edges),
    )
    logger.info("Nodes CSV: %s", nodes_path)
    logger.info("Edges CSV: %s", edges_path)

    return nodes_path, edges_path

