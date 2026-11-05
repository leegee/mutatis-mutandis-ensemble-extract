
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from diachronic_agents.workflows.diachronic_task import SearchResult
from mutatis_mutandis.lib.corpus_logging import get_logger


logger = get_logger(__name__)

SCHEMA_VERSION = 1


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
        raise ValueError( f"SearchResult schema version does not match the store version ({SCHEMA_VERSION})." )

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

    with path.open("r", encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)

    version = data.get("schema_version", 1)

    if version != SCHEMA_VERSION:
        raise ValueError( f"Unsupported SearchResult schema version: {version}" )

    result = SearchResult.from_dict(data)

    logger.info("Loaded SearchResult: %s", path)

    return result

