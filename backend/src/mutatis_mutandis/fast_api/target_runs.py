
from pathlib import Path
import hashlib
import html
import textwrap

import numpy as np
import orjson

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from plotly.colors import qualitative

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.cluster.visualization_data import (
    build_cluster_traces,
    fetch_cluster_interpretations,
    fetch_occurrences,
)


router = APIRouter(prefix="/target-runs", tags=["target-runs"])

CACHE_DIR = Path(OUT_DIR) / "target_runs" / "_viz_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = qualitative.Dark24


def _cache_key(
    run_id: str,
    words: int,
    min_year: int | None,
    max_year: int | None,
    noise: bool,
    wrap_width: int,
    point_size: int,
) -> Path:
    raw = (
        f"viz-v2|{run_id}|{words}|{min_year}|{max_year}|"
        f"{noise}|{wrap_width}|{point_size}"
    )
    h = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{run_id}.{h}.json"


def wrap_html(text: str, width: int = 60) -> str:
    """Format passage text for Plotly hover/customdata."""
    text = " ".join(str(text or "").split())
    text = html.escape(text)
    return "<br>".join(textwrap.wrap(text, width=width))


def _cluster_label(cluster: int, interpretations: dict) -> str:
    interpretation = interpretations.get(cluster, {})
    category = interpretation.get("category", "").strip()

    if category:
        return f"Cluster {cluster} · {category}"

    return f"Cluster {cluster}"


def _build_docs(metadata: dict) -> list[dict]:
    """Build a unique document lookup for the frontend."""
    docs = []
    seen = set()

    for oid, row in metadata.items():
        key = (row["corpus"], row["doc_id"])

        if key in seen:
            continue

        seen.add(key)

        docs.append({
            "corpus": row["corpus"],
            "docId": row["doc_id"],
            "author": row.get("author") or "",
            "title": row.get("title") or "",
        })

    return docs


@router.get(
    "/{run_id}/visualization",
    response_class=ORJSONResponse,
)
def get_visualization(
    run_id: str,
    words: int = Query(20, ge=0, le=100),
    min_year: int | None = None,
    max_year: int | None = None,
    noise: bool = False,
    wrap_width: int = Query(60, ge=20, le=150),
    point_size: int = Query(5, ge=1, le=20),
):
    if min_year is not None and max_year is not None:
        if min_year > max_year:
            raise HTTPException(422, "min_year must not exceed max_year")

    cache_path = _cache_key( run_id, words, min_year, max_year, noise, wrap_width, point_size, )

    if cache_path.exists():
        return orjson.loads(cache_path.read_bytes())

    npz_path = Path(OUT_DIR) / "target_runs" / f"{run_id}.npz"

    if not npz_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Cannot find clustering output for run {run_id}",
        )

    data = np.load(npz_path, allow_pickle=False)

    ids = data["occurrence_id"].astype(str)
    xy = data["e2"]
    labels = data["labels"].astype(int)
    probs = data["probs"]

    if not (len(ids) == len(xy) == len(labels) == len(probs)):
        raise HTTPException(
            status_code=500,
            detail="The clustering output arrays have inconsistent lengths",
        )

    conn = get_connection(application_name="target-run-visualization")

    try:
        metadata = fetch_occurrences(
            conn,
            ids.tolist(),
            words,
            min_year,
            max_year,
        )
        interpretations = fetch_cluster_interpretations(conn, run_id)
    finally:
        conn.close()

    # Match the CLI's pre-filtering behaviour.
    if min_year is not None or max_year is not None:
        keep = np.fromiter(
            (oid in metadata for oid in ids),
            dtype=bool,
            count=len(ids),
        )

        ids = ids[keep]
        xy = xy[keep]
        labels = labels[keep]
        probs = probs[keep]

    traces, docs = build_cluster_traces(
        ids,
        xy,
        labels,
        probs,
        metadata,
        interpretations,
        wrap_width=wrap_width,
        point_size=point_size,
        noise=noise,
    )

    years = [
        m["year"]
        for m in metadata.values()
        if m["year"] is not None
    ]

    year_bounds = (
        [int(min(years)), int(max(years))]
        if years
        else None
    )

    return {
        "run_id": run_id,
        "traces": traces,
        "docs": docs,
        "n_points": len(ids),
        "n_clusters": len(set(labels[labels >= 0].tolist())),
        "n_noise": int((labels == -1).sum()),
        "yearBounds": year_bounds,
    }
