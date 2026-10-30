"""
mutatis_mutandis/core.py

Framework-free retrieval primitives for MacBERTh passage embeddings stored
in year-bucketed LanceDB tables. No argparse, no logging config, no web
framework: safe to import from the CLI, the API, notebooks, or tests.

Ranking
-------
Without negatives, results are ordered by cosine distance (ascending).

With negatives, each table is queried for `limit * overfetch` candidates,
which are re-ranked by

    score = cos(query, doc) - beta * cos(negative_centroid, doc)

(higher is better) and truncated to `limit`.

Because each table contributes a bounded number of candidates, the merged
list is not guaranteed to be the exact global top-k when search is
approximate.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from mutatis_mutandis.lib.corpus_config import LANCE_MODEL_NAME
from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger("passage_search.core")

RESULT_COLUMNS = [
    "passage_id",
    "corpus",
    "doc_id",
    "pub_year",
    "scale",          # new
    "char_start",     # optional but useful
    "word_start",
    "word_end",
    "token_start",
    "token_end",
    "_distance",
]


class VectorNotFoundError(ValueError):
    """No stored vector exists for the requested passage_id."""


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def normalise_vector(vector, description: str = "vector") -> np.ndarray:
    """Return a finite, L2-normalised float32 copy of `vector`."""
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)

    if not np.isfinite(vector).all():
        raise ValueError(f"{description} contains NaN or infinity")

    norm = np.linalg.norm(vector)
    if norm < 1e-12:
        raise ValueError(f"{description} has zero magnitude")

    return vector / norm


# ---------------------------------------------------------------------------
# Table selection
# ---------------------------------------------------------------------------

def table_prefix(representation: str) -> str:
    return f"passage_{representation}__{LANCE_MODEL_NAME}__"


def candidate_tables(db, representation: str, start_year: int, end_year: int):
    """Names of existing tables whose year bucket overlaps the range."""
    prefix = table_prefix(representation)
    names = []

    for name in db.list_tables().tables:
        if not name.startswith(prefix):
            continue
        try:
            b_start, b_end = (int(x) for x in name[len(prefix):].split("_"))
        except ValueError:
            logger.warning("Skipping table with unparseable name: %s", name)
            continue
        if b_start <= end_year and b_end >= start_year:
            names.append(name)

    return sorted(names)


# ---------------------------------------------------------------------------
# Stored vectors
# ---------------------------------------------------------------------------

def load_passage_vector(db, passage_id: str, representation: str) -> np.ndarray:
    """Load an existing passage's stored vector (L2-normalised)."""
    prefix = table_prefix(representation)
    escaped_id = passage_id.replace("'", "''")
    matches = []

    for table_name in db.list_tables().tables:
        if not table_name.startswith(prefix):
            continue

        table = db.open_table(table_name)
        rows = (
            table.search()
            .where(f"passage_id = '{escaped_id}'")
            .limit(2)
            .to_list()
        )
        for row in rows:
            matches.append((table_name, row))

    if not matches:
        raise VectorNotFoundError(
            f"No vector found for passage_id={passage_id!r}, "
            f"representation={representation!r}"
        )

    if len(matches) > 1:
        locations = [name for name, _ in matches]
        raise ValueError(
            f"Multiple vectors found for passage_id={passage_id!r}: "
            f"{locations}"
        )

    table_name, row = matches[0]
    vector = normalise_vector(row["vector"], "Stored passage vector")

    logger.info(
        "Loaded vector %s from %s (doc_id=%s, year=%s)",
        passage_id,
        table_name,
        row.get("doc_id"),
        row.get("pub_year"),
    )
    return vector


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_passages(
    db,
    query_vector,
    representation: str,
    start_year: int,
    end_year: int,
    limit: int,
    include_vectors: bool = False,
    negative_vectors: Optional[List[np.ndarray]] = None,
    beta: float = 0.5,
    overfetch: int = 5,
):
    """Search year-bucketed tables with optional negative re-ranking."""
    query_vec = normalise_vector(query_vector, "Query vector")
    use_negatives = bool(negative_vectors)
    need_vectors = include_vectors or use_negatives

    columns = list(RESULT_COLUMNS)
    if need_vectors:
        columns.append("vector")

    per_table_limit = limit * max(1, overfetch) if use_negatives else limit

    results = []

    for name in candidate_tables(db, representation, start_year, end_year):
        table = db.open_table(name)

        arrow = (
            table.search(query_vec, vector_column_name="vector")
            .metric("cosine")
            .where(
                f"pub_year >= {int(start_year)} "
                f"AND pub_year <= {int(end_year)}"
                + (f" AND scale = '{scale}'" if scale else "")
            )
            .select(columns)
            .limit(per_table_limit)
            .to_arrow()
        )

        for row in arrow.to_pylist():
            distance = row.get("_distance")
            if distance is None:
                raise RuntimeError(
                    "Lance search returned no _distance column. "
                    "Check the installed LanceDB API."
                )
            row["distance"] = float(distance)
            row["table"] = name
            if need_vectors and "vector" in row:
                row["vector"] = np.asarray(row["vector"], dtype=np.float32)
            results.append(row)

    if not results:
        return []

    if use_negatives:
        neg = np.stack(
            [normalise_vector(v, "Negative vector") for v in negative_vectors]
        )
        neg_centroid = normalise_vector(neg.mean(axis=0), "Negative centroid")

        for row in results:
            doc_vec = normalise_vector(row["vector"], "Document vector")
            sim_q = float(np.dot(query_vec, doc_vec))
            sim_neg = float(np.dot(neg_centroid, doc_vec))
            row["sim_q"] = sim_q
            row["sim_neg"] = sim_neg
            row["score"] = sim_q - beta * sim_neg

        results.sort(key=lambda r: r["score"], reverse=True)
    else:
        results.sort(key=lambda r: r["distance"])

    results = results[:limit]

    if not include_vectors:
        for row in results:
            row.pop("vector", None)

    return results
