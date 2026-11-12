"""
scripts/exact_search.py

Diagnostic mirror of mutatis_mutandis.core.search_passages() that bypasses the
approximate (IVF) vector index. Same signature subset, same row shape, same
per-table merge; the only difference is `.bypass_vector_index()`, which makes
Lance scan every row that matches the filter and compute exact distances.

Used by the diagnostic scripts behind their --exact flag. In production the
same effect is a one-parameter change to core.search_passages (see
production_exact_switch.diff).
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from mutatis_mutandis.core import RESULT_COLUMNS, candidate_tables, normalise_vector
from mutatis_mutandis.lib.corpus_config import PASSAGE_SCALES


def search_passages_exact(
    db,
    query_vector,
    representation: str,
    start_year: int,
    end_year: int,
    limit: int,
    include_vectors: bool = False,
    negative_vectors: Optional[List[np.ndarray]] = None,
    beta: float = 0.5,       # accepted for signature compatibility; unused
    overfetch: int = 5,      # accepted for signature compatibility; unused
    scale: Optional[str] = None,
):
    if negative_vectors or include_vectors:
        raise NotImplementedError("exact diagnostic search supports plain queries only")
    if scale is not None and scale not in PASSAGE_SCALES:
        raise ValueError(f"scale must be one of {list(PASSAGE_SCALES)}")

    where = f"pub_year >= {int(start_year)} AND pub_year <= {int(end_year)}"
    if scale:
        where += f" AND scale = '{scale}'"

    query_vec = normalise_vector(query_vector, "Query vector")
    results = []
    for name in candidate_tables(db, representation, start_year, end_year):
        arrow = (
            db.open_table(name)
            .search(query_vec, vector_column_name="vector")
            .metric("cosine")
            .bypass_vector_index()
            .where(where)
            .select(list(RESULT_COLUMNS))
            .limit(limit)
            .to_arrow()
        )
        for row in arrow.to_pylist():
            row["distance"] = float(row["_distance"])
            row["table"] = name
            results.append(row)

    results.sort(key=lambda r: r["distance"])
    return results[:limit]


def get_search_fn(exact: bool):
    """Return search_passages (production) or the exact diagnostic mirror."""
    if exact:
        return search_passages_exact
    from mutatis_mutandis.core import search_passages
    return search_passages