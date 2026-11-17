#!/usr/bin/env python

"""
41_cluster_targets.py - cluster and project the per-occurrence vectors.

Reads the target-occurrence table written by 31_import_targets_to_lance.py and
writes, to Postgres (all keyed by run_id, so runs can be compared side by side):

    target_occurrence        occurrence metadata (once per occurrence)
    target_projection_run    parameters, timings and confound diagnostics
    target_projection        x, y, cluster, membership probability per occurrence
    target_cluster_summary   per-cluster stats + exemplar ids

Pipeline
--------
    vectors (target | context | target-context, one layer)
      -> centre (none | global | per surface form | per document)
      -> L2 normalise -> PCA(50)
      -> UMAP 15-d   (used for clustering)
      -> UMAP 2-d    (used only for display)
      -> HDBSCAN on the 15-d coordinates, never on the 2-d plot

UMAP and PCA are fitted on a random sample (--fit-sample) and every other row is
transformed into that space, so coordinates exist for all rows without fitting 500k
points. HDBSCAN runs on all rows.

The question this is built to answer is whether clusters track USES of the word or
confounds. After clustering it reports the normalised mutual information between
the clusters and: surface form, document, corpus, decade, and route. High NMI with
form or document means the clusters mostly reflect spelling or text, not use.
Run several variants (--centre, --role, --layer) and compare the diagnostics.

    python 41_cluster_targets.py --layer l8 --role target --centre form
    python 41_cluster_targets.py --layer l8 --role target --centre global
    python 41_cluster_targets.py --layer l8 --role diff   --centre form
    python 41_cluster_targets.py --limit 20000        # quick dev run

Requires: numpy pyarrow lancedb scikit-learn umap-learn hdbscan
(sklearn's own HDBSCAN is quadratic; it is only used as a fallback for n <= 100k).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, LANCE_MODEL_NAME, OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger("targets-cluster")

# Must match 31_import_targets_to_lance.py (move both into corpus_config once settled).
TARGETS_LANCE_DIR = Path(LANCE_INDEXES_DIR).parent / "lance_albinism_targets"
TABLE_NAME = f"target_occurrence__{LANCE_MODEL_NAME}"
DIM = 768
LAYERS = ("l8", "last", "mean4")

META_COLUMNS = [
    "occurrence_id", "corpus", "doc_id", "pub_year", "hit_idx", "matched_token",
    "hit_groups", "routes", "token_start", "token_end",
]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS target_occurrence (
    occurrence_id  text PRIMARY KEY,
    corpus         text NOT NULL,
    doc_id         text NOT NULL,
    pub_year       integer NOT NULL,
    hit_idx        integer NOT NULL,
    matched_token  text,
    hit_groups     text,
    routes         text,
    token_start    integer,
    token_end      integer
);

CREATE TABLE IF NOT EXISTS target_projection_run (
    run_id      text PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    params      jsonb NOT NULL,
    metrics     jsonb
);

CREATE TABLE IF NOT EXISTS target_projection (
    run_id         text NOT NULL REFERENCES target_projection_run (run_id) ON DELETE CASCADE,
    occurrence_id  text NOT NULL,
    x              real NOT NULL,
    y              real NOT NULL,
    cluster        integer NOT NULL,         -- -1 = noise
    prob           real,
    PRIMARY KEY (run_id, occurrence_id)
);
CREATE INDEX IF NOT EXISTS target_projection_cluster_idx
    ON target_projection (run_id, cluster);

CREATE TABLE IF NOT EXISTS target_cluster_summary (
    run_id    text NOT NULL REFERENCES target_projection_run (run_id) ON DELETE CASCADE,
    cluster   integer NOT NULL,
    n         integer NOT NULL,
    stats     jsonb NOT NULL,
    nearest   jsonb NOT NULL,                -- occurrence_ids nearest the cluster centre
    sample    jsonb NOT NULL,                -- random members (unbiased look)
    PRIMARY KEY (run_id, cluster)
);
"""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _matrix(column) -> np.ndarray:
    arr = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    flat = arr.flatten().to_numpy(zero_copy_only=False)
    return flat.reshape(-1, DIM).astype(np.float32, copy=False)


def load_occurrences(layer: str, role: str, limit: int | None, seed: int):
    """Return (meta dict of python lists, vector matrix float32)."""
    import lancedb

    vec_cols = {
        "target": [f"vec_target_{layer}"],
        "context": [f"vec_context_{layer}"],
        "diff": [f"vec_target_{layer}", f"vec_context_{layer}"],
    }[role]
    cols = META_COLUMNS + vec_cols

    table = lancedb.connect(str(TARGETS_LANCE_DIR)).open_table(TABLE_NAME)
    logger.info("loading %s from %s (%d rows)", vec_cols, TABLE_NAME, table.count_rows())
    try:
        arrow = table.to_lance().to_table(columns=cols)
    except Exception:                                    # older / different API
        arrow = table.search().select(cols).limit(table.count_rows()).to_arrow()

    if limit and arrow.num_rows > limit:
        rng = np.random.default_rng(seed)
        keep = np.sort(rng.choice(arrow.num_rows, size=limit, replace=False))
        arrow = arrow.take(pa.array(keep))
        logger.info("--limit: using a random %d rows", limit)

    meta = {name: arrow.column(name).to_pylist() for name in META_COLUMNS}

    if role == "diff":
        X = _matrix(arrow.column(vec_cols[0])) - _matrix(arrow.column(vec_cols[1]))
    else:
        X = _matrix(arrow.column(vec_cols[0]))
    return meta, X


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def centre(X: np.ndarray, mode: str, keys: list[str], min_count: int) -> np.ndarray:
    """
    Subtract a mean from every row.

    form / doc: the mean of the row's surface form (or document). Groups with fewer
    than min_count rows share one pooled "__rare__" group so their means are not noise.
    """
    if mode == "none":
        return X
    if mode == "global":
        return X - X.mean(axis=0, keepdims=True)

    counts = Counter(keys)
    bucket = np.array([k if counts[k] >= min_count else "__rare__" for k in keys])
    uniques, inverse = np.unique(bucket, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    sizes = np.bincount(inverse, minlength=len(uniques))
    starts = np.concatenate(([0], np.cumsum(sizes)[:-1]))
    sums = np.add.reduceat(X[order], starts, axis=0)
    means = (sums / sizes[:, None]).astype(np.float32)
    logger.info(
        "centre=%s: %d groups (%d rows pooled as rare, threshold %d)",
        mode, len(uniques), int((bucket == "__rare__").sum()), min_count,
    )
    return X - means[inverse]


def l2_normalise(X: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.clip(norms, 1e-8, None)


# ---------------------------------------------------------------------------
# Reduction and clustering
# ---------------------------------------------------------------------------

def fit_transform_sampled(model, Z: np.ndarray, fit_idx: np.ndarray, chunk: int = 50_000):
    """Fit on Z[fit_idx], return coordinates for all rows (transform for the rest)."""
    n = Z.shape[0]
    if len(fit_idx) == n:
        return model.fit_transform(Z)

    model.fit(Z[fit_idx])
    emb = model.embedding_
    out = np.empty((n, emb.shape[1]), dtype=np.float32)
    out[fit_idx] = emb
    rest = np.setdiff1d(np.arange(n), fit_idx, assume_unique=True)
    for s in range(0, len(rest), chunk):
        part = rest[s:s + chunk]
        out[part] = model.transform(Z[part])
    return out


def run_hdbscan(E: np.ndarray, min_cluster_size: int, min_samples: int, method: str):
    try:
        import hdbscan
    except ImportError:
        if E.shape[0] > 100_000:
            raise SystemExit(
                "pip install hdbscan: sklearn's HDBSCAN is quadratic and not "
                "practical above ~100k rows."
            )
        from sklearn.cluster import HDBSCAN
        logger.warning("hdbscan package missing; using sklearn.cluster.HDBSCAN")
        model = HDBSCAN(
            min_cluster_size=min_cluster_size, min_samples=min_samples,
            cluster_selection_method=method, n_jobs=-1,
        ).fit(E)
        return model.labels_.astype(np.int32), model.probabilities_.astype(np.float32)

    model = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=method,
        core_dist_n_jobs=-1,
    ).fit(E)
    return model.labels_.astype(np.int32), model.probabilities_.astype(np.float32)


# ---------------------------------------------------------------------------
# Diagnostics and summaries
# ---------------------------------------------------------------------------

def _codes(values) -> np.ndarray:
    return np.unique(np.asarray(values, dtype=object).astype(str), return_inverse=True)[1]


def confound_metrics(labels: np.ndarray, meta: dict) -> dict:
    """NMI between cluster labels (noise excluded) and potential confounds."""
    from sklearn.metrics import normalized_mutual_info_score as nmi

    keep = labels >= 0
    if keep.sum() < 2 or len(set(labels[keep].tolist())) < 2:
        return {"note": "fewer than two clusters; no diagnostics"}

    sel = np.flatnonzero(keep)
    pick = lambda name: [meta[name][i] for i in sel]
    forms = [str(t).lower() for t in pick("matched_token")]
    docs = [f"{c}/{d}" for c, d in zip(pick("corpus"), pick("doc_id"))]
    decades = [y // 10 * 10 for y in pick("pub_year")]
    routes = ["+".join(r) if isinstance(r, list) else str(r) for r in pick("routes")]

    lab = labels[keep]
    result = {
        "nmi_form": float(nmi(_codes(forms), lab)),
        "nmi_doc": float(nmi(_codes(docs), lab)),
        "nmi_corpus": float(nmi(_codes(pick("corpus")), lab)),
        "nmi_decade": float(nmi(_codes(decades), lab)),
        "nmi_route": float(nmi(_codes(routes), lab)),
        "n_forms": len(set(forms)),
        "n_docs": len(set(docs)),
    }
    return result


def cluster_summaries(labels, probs, E15, meta, n_exemplars: int, seed: int):
    rng = np.random.default_rng(seed)
    ids = meta["occurrence_id"]
    years = np.asarray(meta["pub_year"])
    forms = [str(t).lower() for t in meta["matched_token"]]
    docs = [f"{c}/{d}" for c, d in zip(meta["corpus"], meta["doc_id"])]
    routes = ["+".join(r) if isinstance(r, list) else str(r) for r in meta["routes"]]
    groups = ["+".join(g) if isinstance(g, list) else str(g) for g in meta["hit_groups"]]
    corpora = meta["corpus"]

    order = np.argsort(labels, kind="stable")
    sorted_labels = labels[order]
    cuts = np.flatnonzero(np.diff(sorted_labels)) + 1
    groups_idx = np.split(order, cuts)

    out = []
    n_total = len(labels)
    for members in groups_idx:
        c = int(labels[members[0]])
        doc_counts = Counter(docs[i] for i in members)
        stats = {
            "share": round(len(members) / n_total, 5),
            "year_min": int(years[members].min()),
            "year_p10": float(np.percentile(years[members], 10)),
            "year_median": float(np.median(years[members])),
            "year_p90": float(np.percentile(years[members], 90)),
            "year_max": int(years[members].max()),
            "n_docs": len(doc_counts),
            "top_doc": doc_counts.most_common(1)[0][0],
            "top_doc_share": round(doc_counts.most_common(1)[0][1] / len(members), 4),
            "forms": Counter(forms[i] for i in members).most_common(8),
            "routes": Counter(routes[i] for i in members).most_common(6),
            "groups": Counter(groups[i] for i in members).most_common(6),
            "corpora": Counter(corpora[i] for i in members).most_common(5),
            "mean_prob": round(float(probs[members].mean()), 4),
        }
        if c >= 0:
            centre_pt = E15[members].mean(axis=0)
            dist = np.linalg.norm(E15[members] - centre_pt, axis=1)
            nearest = members[np.argsort(dist)[:n_exemplars]]
        else:
            nearest = members[:0]
        sample = rng.choice(members, size=min(n_exemplars, len(members)), replace=False)
        out.append({
            "cluster": c,
            "n": int(len(members)),
            "stats": stats,
            "nearest": [ids[i] for i in nearest],
            "sample": [ids[i] for i in sample],
        })
    out.sort(key=lambda r: (r["cluster"] == -1, -r["n"]))
    return out


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------

def insert_batches(cur, sql: str, columns: list[list], lead: tuple = (),
                   size: int = 20_000) -> None:
    """
    Driver-agnostic bulk insert: one statement per batch, arrays unnested server-side.
    `lead` are scalar parameters that come before the array parameters.
    """
    n = len(columns[0])
    for start in range(0, n, size):
        cur.execute(sql, [*lead, *(col[start:start + size] for col in columns)])


def write_results(conn, run_id, params, metrics, meta, E2, labels, probs, summaries):
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)

        joined = lambda v: ",".join(v) if isinstance(v, list) else str(v)
        insert_batches(
            cur,
            """
            INSERT INTO target_occurrence
              (occurrence_id, corpus, doc_id, pub_year, hit_idx, matched_token,
               hit_groups, routes, token_start, token_end)
            SELECT * FROM unnest(%s::text[], %s::text[], %s::text[], %s::int[], %s::int[],
                                 %s::text[], %s::text[], %s::text[], %s::int[], %s::int[])
            ON CONFLICT (occurrence_id) DO NOTHING
            """,
            [
                meta["occurrence_id"], meta["corpus"], meta["doc_id"],
                [int(v) for v in meta["pub_year"]], [int(v) for v in meta["hit_idx"]],
                meta["matched_token"],
                [joined(v) for v in meta["hit_groups"]],
                [joined(v) for v in meta["routes"]],
                [int(v) for v in meta["token_start"]], [int(v) for v in meta["token_end"]],
            ],
        )

        cur.execute(
            "INSERT INTO target_projection_run (run_id, params, metrics) "
            "VALUES (%s, %s::jsonb, %s::jsonb)",
            (run_id, json.dumps(params), json.dumps(metrics)),
        )

        insert_batches(
            cur,
            """
            INSERT INTO target_projection (run_id, occurrence_id, x, y, cluster, prob)
            SELECT %s::text, * FROM unnest(%s::text[], %s::real[], %s::real[], %s::int[], %s::real[])
            """,
            [
                meta["occurrence_id"],
                E2[:, 0].astype(float).tolist(), E2[:, 1].astype(float).tolist(),
                labels.astype(int).tolist(), probs.astype(float).tolist(),
            ],
            lead=(run_id,),
        )

        for s in summaries:
            cur.execute(
                "INSERT INTO target_cluster_summary (run_id, cluster, n, stats, nearest, sample) "
                "VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)",
                (run_id, s["cluster"], s["n"], json.dumps(s["stats"]),
                 json.dumps(s["nearest"]), json.dumps(s["sample"])),
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--layer", choices=LAYERS, default="l8")
    p.add_argument("--role", choices=("target", "context", "diff"), default="target",
                   help="diff = target minus context")
    p.add_argument("--centre", choices=("none", "global", "form", "doc"), default="form")
    p.add_argument("--min-group", type=int, default=30,
                   help="min rows for a form/document to get its own centring mean")
    p.add_argument("--pca", type=int, default=50)
    p.add_argument("--fit-sample", type=int, default=200_000,
                   help="rows used to fit PCA/UMAP; all rows are transformed")
    p.add_argument("--n-neighbors", type=int, default=30)
    p.add_argument("--cluster-dims", type=int, default=15)
    p.add_argument("--min-cluster-size", type=int, default=40)
    p.add_argument("--min-samples", type=int, default=10)
    p.add_argument("--selection", choices=("eom", "leaf"), default="eom",
                   help="leaf gives finer, more numerous clusters")
    p.add_argument("--exemplars", type=int, default=12)
    p.add_argument("--limit", type=int, default=None, help="random subset, for dev runs")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--run-id", default=None)
    p.add_argument("--out-dir", default=OUT_DIR / "target_runs",
                   help="npz of ids + coordinates + labels is saved here")
    args = p.parse_args()

    t_start = time.perf_counter()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"{args.layer}-{args.role}-{args.centre}-{stamp}"
    logger.info("run_id=%s", run_id)

    meta, X = load_occurrences(args.layer, args.role, args.limit, args.seed)
    n = X.shape[0]
    logger.info("%d occurrences, vectors %s", n, X.shape)

    if args.centre == "form":
        keys = [str(t).lower() for t in meta["matched_token"]]
    else:
        keys = [f"{c}/{d}" for c, d in zip(meta["corpus"], meta["doc_id"])]
    X = centre(X, args.centre, keys, args.min_group)
    X = l2_normalise(X)

    rng = np.random.default_rng(args.seed)
    fit_idx = np.sort(rng.choice(n, size=min(n, args.fit_sample), replace=False))
    logger.info("fitting on %d of %d rows", len(fit_idx), n)

    from sklearn.decomposition import PCA
    import umap

    t0 = time.perf_counter()
    pca = PCA(n_components=min(args.pca, X.shape[1], len(fit_idx) - 1), random_state=args.seed)
    pca.fit(X[fit_idx])
    Z = pca.transform(X).astype(np.float32)
    del X
    logger.info("PCA: %.1f%% variance kept (%.0fs)",
                100 * pca.explained_variance_ratio_.sum(), time.perf_counter() - t0)

    t0 = time.perf_counter()
    E15 = fit_transform_sampled(
        umap.UMAP(n_components=args.cluster_dims, n_neighbors=args.n_neighbors,
                  min_dist=0.0, metric="cosine"),
        Z, fit_idx,
    ).astype(np.float32)
    logger.info("UMAP %dd done (%.0fs)", args.cluster_dims, time.perf_counter() - t0)

    t0 = time.perf_counter()
    E2 = fit_transform_sampled(
        umap.UMAP(n_components=2, n_neighbors=args.n_neighbors,
                  min_dist=0.1, metric="cosine"),
        Z, fit_idx,
    ).astype(np.float32)
    logger.info("UMAP 2d done (%.0fs)", time.perf_counter() - t0)

    t0 = time.perf_counter()
    labels, probs = run_hdbscan(E15, args.min_cluster_size, args.min_samples, args.selection)
    n_clusters = int(labels.max()) + 1 if (labels >= 0).any() else 0
    n_noise = int((labels < 0).sum())
    logger.info("HDBSCAN: %d clusters, %d noise rows (%.1f%%) (%.0fs)",
                n_clusters, n_noise, 100 * n_noise / n, time.perf_counter() - t0)

    metrics = confound_metrics(labels, meta)
    metrics.update({
        "n": n, "n_clusters": n_clusters, "noise_fraction": round(n_noise / n, 4),
        "pca_variance": round(float(pca.explained_variance_ratio_.sum()), 4),
        "seconds": round(time.perf_counter() - t_start, 1),
    })
    summaries = cluster_summaries(labels, probs, E15, meta, args.exemplars, args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_dir / f"{run_id}.npz",
        occurrence_id=np.asarray(meta["occurrence_id"]), e2=E2, e15=E15,
        labels=labels, probs=probs,
    )

    params = dict(vars(args), run_id=run_id, lance_table=TABLE_NAME,
                  params_hash=hashlib.sha1(json.dumps(vars(args), sort_keys=True,
                                                      default=str).encode()).hexdigest()[:10])
    conn = get_connection(application_name="cluster-targets")
    try:
        write_results(conn, run_id, params, metrics, meta, E2, labels, probs, summaries)
    finally:
        conn.close()

    logger.info("=== %s ===", run_id)
    logger.info("clusters=%d noise=%.1f%%", n_clusters, 100 * n_noise / n)
    for key in ("nmi_form", "nmi_doc", "nmi_corpus", "nmi_decade", "nmi_route"):
        if key in metrics:
            logger.info("  %-11s %.3f", key, metrics[key])
    logger.info("Inspect: python 42_inspect_clusters.py --run-id %s", run_id)


if __name__ == "__main__":
    main()
