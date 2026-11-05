from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime

from diachronic_agents.workflows.diachronic_task import SearchResult
from mutatis_mutandis.lib.corpus_logging import get_logger


logger = get_logger(__name__)

SCHEMA_VERSION = 1


def _read_archive_data(path: Path) -> dict[str, Any]:
    """Read and validate an archived SearchResult dictionary."""

    with path.open("r", encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid SearchResult archive: {path}")

    version = data.get("schema_version", 1)

    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported SearchResult schema version: {version}"
        )

    return data


def save_search_result(
    result: SearchResult,
    path: str | Path,
) -> Path:
    """
    Save a SearchResult as JSON.

    Writes to a temporary file first, then atomically replaces
    the destination to avoid incomplete output files.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = result.to_dict()

    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"SearchResult schema version does not match "
            f"the store version ({SCHEMA_VERSION})."
        )

    temporary_path = path.with_name(
        f".{path.name}.{uuid4().hex}.tmp"
    )

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            file.write("\n")

        os.replace(temporary_path, path)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    logger.info("Saved SearchResult: %s", path)

    return path


def load_search_result(
    path: str | Path,
) -> SearchResult:
    """Load a SearchResult from a JSON archive."""

    path = Path(path)
    data = _read_archive_data(path)

    result = SearchResult.from_dict(data)

    logger.info("Loaded SearchResult: %s", path)

    return result


def get_search_result_summary(
    path: str | Path,
) -> dict[str, Any]:
    """
    Return lightweight metadata about an archived SearchResult.

    Does not reconstruct the SearchResult object.
    """

    path = Path(path)
    data = _read_archive_data(path)

    results = data.get("results", {})
    graphs = data.get("graphs", {})
    cumulative_graph = data.get("cumulative_graph", {})
    metadata = cumulative_graph.get("metadata", {})

    passage_count = sum(
        len(period_result.get("passages", []))
        for period_result in results.values()
    )

    stat = path.stat()

    return {
        "path": str(path),
        "filename": path.name,
        "saved_at": datetime.fromtimestamp(
            stat.st_mtime
        ).astimezone().isoformat(timespec="seconds"),
        "size_bytes": stat.st_size,
        "query": data.get("query"),
        "direction": data.get("direction"),
        "initial_period": data.get("initial_period"),
        "target_period": data.get("target_period"),
        "periods": data.get("periods", []),
        "period_count": len(data.get("periods", [])),
        "result_period_count": len(results),
        "graph_period_count": len(graphs),
        "passage_count": passage_count,
        "classification_period_count": len(
            data.get("classifications", {})
        ),
        "prospect_period_count": len(
            data.get("prospects", {})
        ),
        "node_count": metadata.get("node_count", 0),
        "edge_count": metadata.get("edge_count", 0),
        "search_count": metadata.get(
            "search_count",
            len(metadata.get("search_runs", [])),
        ),
    }


def list_search_results(
    directory: str | Path,
) -> list[dict[str, Any]]:
    """
    List valid SearchResult archives in a directory.

    Results are ordered newest first.
    Invalid archives are logged and skipped.
    """

    directory = Path(directory)

    if not directory.exists():
        return []

    if not directory.is_dir():
        raise NotADirectoryError(directory)

    summaries = []

    for path in directory.glob("*.json"):
        try:
            summaries.append(
                get_search_result_summary(path)
            )

        except Exception:
            logger.warning(
                "Skipping invalid SearchResult archive: %s",
                path,
                exc_info=True,
            )

    return sorted(
        summaries,
        key=lambda item: item["saved_at"],
        reverse=True,
    )
