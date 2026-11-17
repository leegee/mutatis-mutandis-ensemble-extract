#!/usr/bin/env python
"""
43_visualise_clusters.py - interactive dark UMAP plot of a clustering run.

Reads the .npz written by 41_cluster_targets.py and passage text/metadata from
Postgres. Writes a self-contained HTML plot (Plotly JS is embedded).

Examples:
    python 43_visualise_clusters.py --run-id l8-target-form-20261118-101500
    python 43_visualise_clusters.py --run-id YOUR_RUN --words 20
    python 43_visualise_clusters.py --run-id YOUR_RUN --out out/target_runs/clusters.html

Install:
    pip install plotly
"""

from __future__ import annotations

import argparse
import html
import textwrap
from pathlib import Path

import numpy as np

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection


def wrap_html(value: object, width: int = 40) -> str:
    """Wrap text for Plotly hover labels, escaping corpus text as HTML."""
    value = " ".join(str(value or "").split())
    escaped = html.escape(value)
    return "<br>".join(
        textwrap.wrap(escaped, width=width, break_long_words=True,
                      break_on_hyphens=False)
    )


def fetch_occurrences(conn, occurrence_ids: list[str], words: int) -> dict:
    """
    Fetch metadata and a token-window passage for each occurrence.

    The lateral subquery uses the occurrence's own hit_idx, rather than searching
    the passage for the surface form (which may occur more than once).
    """
    sql = """
        SELECT
            o.occurrence_id, o.corpus, o.doc_id, o.pub_year, o.hit_idx,
            o.matched_token, d.author, d.title,
            COALESCE(passage.text, '') AS passage
        FROM target_occurrence o
        LEFT JOIN documents d
          ON d.corpus = o.corpus AND d.doc_id = o.doc_id
        LEFT JOIN LATERAL (
            SELECT string_agg(
                CASE WHEN t.token_idx = o.hit_idx
                     THEN '«' || t.token || '»'
                     ELSE t.token
                END,
                ' ' ORDER BY t.token_idx
            ) AS text
            FROM tokens t
            WHERE t.corpus = o.corpus
              AND t.doc_id = o.doc_id
              AND t.token_idx BETWEEN o.hit_idx - %s AND o.hit_idx + %s
        ) passage ON TRUE
        WHERE o.occurrence_id = ANY(%s)
    """
    result = {}
    # Keep parameter batches moderate for large runs.
    batch_size = 10_000
    with conn.cursor() as cur:
        for start in range(0, len(occurrence_ids), batch_size):
            batch = occurrence_ids[start:start + batch_size]
            cur.execute(sql, (words, words, batch))
            for row in cur.fetchall():
                (oid, corpus, doc_id, year, hit_idx, token,
                 author, title, passage) = row
                result[oid] = {
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "year": year,
                    "token": token or "",
                    "author": author or "Unknown author",
                    "title": title or doc_id,
                    "passage": passage or "",
                }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--words", type=int, default=20,
                        help="tokens of context on either side of the hit")
    parser.add_argument("--wrap", type=int, default=40,
                        help="hover-passage wrap width in characters")
    parser.add_argument("--out", default=None, help="output HTML path")
    parser.add_argument("--point-size", type=float, default=5.0)
    parser.add_argument("--noise", action="store_true",
                        help="include HDBSCAN noise (shown in grey)")
    parser.add_argument("--cdn", action="store_true",
                        help="load Plotly from CDN instead of embedding it")
    args = parser.parse_args()

    npz_path = Path(OUT_DIR) / "target_runs" / f"{args.run_id}.npz"
    if not npz_path.exists():
        raise SystemExit(f"Cannot find clustering output: {npz_path}")

    data = np.load(npz_path, allow_pickle=False)
    ids = data["occurrence_id"].astype(str)
    xy = data["e2"]
    labels = data["labels"].astype(int)
    probs = data["probs"]

    if not (len(ids) == len(xy) == len(labels) == len(probs)):
        raise SystemExit("The .npz arrays have inconsistent lengths")

    print(f"Loading metadata and passages for {len(ids):,} occurrences...")
    conn = get_connection(application_name="visualise-target-clusters")
    try:
        metadata = fetch_occurrences(conn, ids.tolist(), args.words)
    finally:
        conn.close()

    missing = len(ids) - len(metadata)
    if missing:
        print(f"Warning: {missing:,} occurrences had no matching metadata row")

    import plotly.graph_objects as go
    from plotly.colors import qualitative

    fig = go.Figure()
    palette = qualitative.Dark24
    cluster_ids = sorted(c for c in set(labels.tolist()) if c >= 0)
    if args.noise and np.any(labels == -1):
        cluster_ids = [-1] + cluster_ids

    for cluster in cluster_ids:
        idx = np.flatnonzero(labels == cluster)
        if not len(idx):
            continue

        custom = []
        for i in idx:
            m = metadata.get(ids[i])
            if m is None:
                custom.append(["?", "Unknown", "No metadata", "", ids[i], 0.0])
                continue

            heading = f"{m['author']}, {m['title']}"
            passage = wrap_html(m["passage"], args.wrap)
            custom.append([
                str(m["year"]),
                wrap_html(heading, args.wrap),
                wrap_html(f"{m['corpus']} / {m['doc_id']}", args.wrap),
                passage,
                ids[i],
                float(probs[i]),
            ])

        is_noise = cluster == -1
        name = "Noise" if is_noise else f"Cluster {cluster} (n={len(idx):,})"
        colour = "#777777" if is_noise else palette[(cluster if cluster >= 0 else 0) % len(palette)]

        fig.add_trace(go.Scattergl(
            x=xy[idx, 0],
            y=xy[idx, 1],
            mode="markers",
            name=name,
            marker=dict(
                size=3 if is_noise else args.point_size,
                color=colour,
                opacity=0.25 if is_noise else 0.78,
            ),
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "%{customdata[0]}<br>"
                "<span style='color:#aaaaaa'>%{customdata[2]}</span><br><br>"
                "%{customdata[3]}<br><br>"
                "<span style='color:#aaaaaa'>"
                "Membership: %{customdata[5]:.2f}<br>"
                "Occurrence: %{customdata[4]}"
                "</span><extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text=f"Target occurrence clusters · {args.run_id}",
            x=0.02,
            xanchor="left",
        ),
        template="plotly_dark",
        paper_bgcolor="#111318",
        plot_bgcolor="#171a21",
        font=dict(family="Segoe UI, Arial, sans-serif", color="#e2e5eb", size=12),
        hoverlabel=dict(
            bgcolor="#252a34",
            bordercolor="#596273",
            font=dict(family="Segoe UI, Arial, sans-serif", size=12,
                      color="#f2f3f5"),
            align="left",
        ),
        xaxis=dict(title="UMAP 1", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        yaxis=dict(title="UMAP 2", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        legend=dict(
            title="Clusters · click to hide/show",
            bgcolor="rgba(20,23,30,0.85)",
            bordercolor="#343b48",
            borderwidth=1,
            itemsizing="constant",
            y=1,
            yanchor="top",
            x=1.02,
        ),
        margin=dict(l=55, r=260, t=75, b=55),
        height=900,
        hovermode="closest",
    )

    out_path = Path(args.out) if args.out else (
        Path(OUT_DIR) / "target_runs" / f"{args.run_id}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(
        str(out_path),
        include_plotlyjs="cdn" if args.cdn else True,
        full_html=True,
        config={
            "scrollZoom": True,
            "displaylogo": False,
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )

    print(f"Saved: {out_path}")
    print(f"Points: {len(ids):,} | clusters: {len(set(labels[labels >= 0])):,} "
          f"| noise: {(labels == -1).sum():,}")
    print(f"Open the HTML file in your browser. {out_path}")


if __name__ == "__main__":
    main()
