#!/usr/bin/env python

"""
42_inspect_clusters.py - read what a clustering run actually contains.

Prints the run's confound diagnostics, a table of clusters, and, for the clusters
you pick, passages with the hit marked «like this». Text comes from the Postgres
`tokens` table, using the occurrence's own hit position.

    python 42_inspect_clusters.py                          # latest run: overview
    python 42_inspect_clusters.py --run-id l8-target-form-20261118-101500
    python 42_inspect_clusters.py --cluster 7              # nearest to centre
    python 42_inspect_clusters.py --cluster 7 --sample     # random members instead
    python 42_inspect_clusters.py --cluster 7 --cluster 12 --n 15 --words 20
    python 42_inspect_clusters.py --top 10 --n 4           # exemplars for the 10 biggest

Look at both --nearest (default) and --sample: nearest-to-centre passages are the
cleanest cases and flatter a cluster; random members show how mixed it really is.
"""

from __future__ import annotations

import argparse
import json

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def latest_run(cur) -> str:
    cur.execute("SELECT run_id FROM target_projection_run ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        raise SystemExit("No runs found in target_projection_run")
    return row[0]


def print_run(cur, run_id: str) -> None:
    cur.execute(
        "SELECT params, metrics, created_at FROM target_projection_run WHERE run_id = %s",
        (run_id,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"Unknown run: {run_id}")
    params, metrics, created = _json(row[0]), _json(row[1]), row[2]

    print(f"\nRun {run_id}   ({created:%Y-%m-%d %H:%M})")
    print(
        f"  layer={params.get('layer')} role={params.get('role')} "
        f"centre={params.get('centre')} min_cluster_size={params.get('min_cluster_size')} "
        f"selection={params.get('selection')}"
    )
    print(
        f"  n={metrics.get('n')}  clusters={metrics.get('n_clusters')}  "
        f"noise={100 * metrics.get('noise_fraction', 0):.1f}%"
    )
    print("  How much do clusters track a confound? (NMI, 0 = none, 1 = identical)")
    for key, label in (
        ("nmi_form", "surface form"), ("nmi_doc", "document"),
        ("nmi_corpus", "corpus"), ("nmi_decade", "decade"), ("nmi_route", "route"),
    ):
        if key in metrics:
            print(f"    {label:<13} {metrics[key]:.3f}")


def print_cluster_table(cur, run_id: str, limit: int) -> None:
    cur.execute(
        """
        SELECT cluster, n, stats FROM target_cluster_summary
        WHERE run_id = %s ORDER BY (cluster = -1), n DESC LIMIT %s
        """,
        (run_id, limit),
    )
    rows = cur.fetchall()
    print(f"\n{'cl':>4} {'n':>7} {'years (p10-p90)':>16} {'docs':>5} {'top-doc':>7}  forms / routes")
    for cluster, n, stats in rows:
        s = _json(stats)
        forms = ", ".join(f"{f} {c}" for f, c in s["forms"][:4])
        routes = ", ".join(f"{r} {c}" for r, c in s["routes"][:2])
        label = "noise" if cluster == -1 else str(cluster)
        print(
            f"{label:>4} {n:>7} {int(s['year_p10']):>8}-{int(s['year_p90']):<7} "
            f"{s['n_docs']:>5} {s['top_doc_share']:>7.0%}  {forms}  |  {routes}"
        )


def passage(cur, corpus, doc_id, hit_idx, words: int) -> str:
    cur.execute(
        """
        SELECT token_idx, token FROM tokens
        WHERE corpus = %s AND doc_id = %s AND token_idx BETWEEN %s AND %s
        ORDER BY token_idx
        """,
        (corpus, doc_id, hit_idx - words, hit_idx + words),
    )
    parts = []
    for idx, token in cur.fetchall():
        parts.append(f"«{token}»" if idx == hit_idx else token)
    return " ".join(parts)


def print_exemplars(cur, run_id: str, cluster: int, n: int, words: int, sample: bool) -> None:
    cur.execute(
        "SELECT n, stats, nearest, sample FROM target_cluster_summary "
        "WHERE run_id = %s AND cluster = %s",
        (run_id, cluster),
    )
    row = cur.fetchone()
    if not row:
        print(f"\nNo cluster {cluster} in run {run_id}")
        return
    size, stats, nearest, rand = row[0], _json(row[1]), _json(row[2]), _json(row[3])
    ids = (rand if sample else nearest)[:n]

    print(f"\n{'=' * 78}")
    print(
        f"Cluster {cluster}: {size} occurrences, "
        f"{stats['year_min']}-{stats['year_max']} (median {stats['year_median']:.0f}), "
        f"{stats['n_docs']} documents (largest {stats['top_doc_share']:.0%})"
    )
    print("  forms:   " + ", ".join(f"{f} {c}" for f, c in stats["forms"]))
    print("  routes:  " + ", ".join(f"{r} {c}" for r, c in stats["routes"]))
    print("  groups:  " + ", ".join(f"{g} {c}" for g, c in stats["groups"]))
    print(f"  --- {'random members' if sample else 'nearest the centre'} ---")

    if not ids:
        print("  (no exemplars stored for this cluster)")
        return

    cur.execute(
        """
        SELECT o.occurrence_id, o.corpus, o.doc_id, o.pub_year, o.hit_idx, d.author, d.title
        FROM target_occurrence o
        LEFT JOIN documents d ON d.corpus = o.corpus AND d.doc_id = o.doc_id
        WHERE o.occurrence_id = ANY(%s)
        """,
        (list(ids),),
    )
    by_id = {r[0]: r for r in cur.fetchall()}
    for oid in ids:
        if oid not in by_id:
            continue
        _, corpus, doc_id, year, hit_idx, author, title = by_id[oid]
        who = f"{author or '?'}, {title or doc_id}"
        print(f"\n  [{year}] {who[:70]}")
        print(f"    {passage(cur, corpus, doc_id, hit_idx, words)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--run-id", default=None, help="default: the most recent run")
    p.add_argument("--cluster", type=int, action="append", default=[],
                   help="cluster id to print exemplars for (repeatable; -1 = noise)")
    p.add_argument("--top", type=int, default=0,
                   help="print exemplars for the N largest clusters")
    p.add_argument("--n", type=int, default=8, help="exemplars per cluster")
    p.add_argument("--words", type=int, default=15, help="words of context each side")
    p.add_argument("--sample", action="store_true",
                   help="random members instead of nearest the centre")
    p.add_argument("--table", type=int, default=30, help="clusters in the overview table")
    args = p.parse_args()

    conn = get_connection(application_name="inspect-clusters")
    try:
        with conn.cursor() as cur:
            run_id = args.run_id or latest_run(cur)
            print_run(cur, run_id)
            print_cluster_table(cur, run_id, args.table)

            wanted = list(args.cluster)
            if args.top:
                cur.execute(
                    "SELECT cluster FROM target_cluster_summary "
                    "WHERE run_id = %s AND cluster >= 0 ORDER BY n DESC LIMIT %s",
                    (run_id, args.top),
                )
                wanted += [r[0] for r in cur.fetchall() if r[0] not in wanted]

            for cluster in wanted:
                print_exemplars(cur, run_id, cluster, args.n, args.words, args.sample)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
