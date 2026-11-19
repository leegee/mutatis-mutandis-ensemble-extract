# target_runs.py
from pathlib import Path
import hashlib, json, orjson

import numpy as np

from fastapi import APIRouter, Query
from fastapi.responses import ORJSONResponse

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.cluster.cluster_targets import (
    OUT_DIR, fetch_occurrences,
    fetch_cluster_interpretations
    )

router = APIRouter(prefix="/api/target-runs", tags=["target-runs"])

CACHE_DIR = Path(OUT_DIR) / "target_runs" / "_viz_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _cache_key(run_id: str, words: int, min_year: int | None, max_year: int | None) -> Path:
    raw = f"{run_id}|{words}|{min_year}|{max_year}"
    h = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{run_id}.{h}.json"

@router.get("/{run_id}/visualization", response_class=ORJSONResponse)
def get_visualization(
    run_id: str,
    words: int = Query(20, ge=0, le=100),
    min_year: int | None = None,
    max_year: int | None = None,
    noise: bool = False,
):
    cache_path = _cache_key(run_id, words, min_year, max_year)
    if cache_path.exists():
        return orjson.loads(cache_path.read_bytes())

    # --- reuse the heavy lifting from the old 45_ script ---
    npz_path = Path(OUT_DIR) / "target_runs" / f"{run_id}.npz"
    if not npz_path.exists():
        raise HTTPException(404, f"Run not found: {run_id}")

    data = np.load(npz_path, allow_pickle=False)
    ids = data["occurrence_id"].astype(str)
    xy = data["e2"]
    labels = data["labels"].astype(int)
    probs = data["probs"]

    with get_connection(application_name="viz-api") as conn:
        metadata = fetch_occurrences(conn, ids.tolist(), words, min_year, max_year)
        interpretations = fetch_cluster_interpretations(conn, run_id)

    # year filter (same logic as before)
    if min_year is not None or max_year is not None:
        keep = np.fromiter((oid in metadata for oid in ids), dtype=bool)
        ids, xy, labels, probs = ids[keep], xy[keep], labels[keep], probs[keep]

    # build docs + traces exactly as the old script did
    # (copy the doc_slot / customdata construction here)
    # ...

    payload = {
        "runId": run_id,
        "nPoints": len(ids),
        "nClusters": len(set(labels[labels >= 0].tolist())),
        "yearBounds": year_bounds,
        "docs": docs,
        "traces": traces,          # list of ClusterTrace-shaped dicts
        "seedTerms": [],           # or accept as query params later
    }

    cache_path.write_bytes(orjson.dumps(payload))
    return payload
