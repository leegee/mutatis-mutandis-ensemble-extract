
from __future__ import annotations

import html
import json
import textwrap

import numpy as np

from mutatis_mutandis.lib.corpus_logging import logger


def wrap_html(value: object, width: int = 60) -> str:
    """Wrap text for Plotly hover labels, escaping corpus text as HTML."""
    value = " ".join(str(value or "").split())
    escaped = html.escape(value)
    return "<br>".join(
        textwrap.wrap(
            escaped,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
        )
    )


def fetch_cluster_interpretations(conn, run_id: str) -> dict[int, dict]:
    """Fetch the LLM interpretation for each cluster in this run."""
    sql = """
        SELECT cluster, classification
        FROM target_cluster_interpretation
        WHERE run_id = %s
          AND prompt_version = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (run_id, "cluster-interpretation-v1"))
        rows = cur.fetchall()

    logger.info(
        "Loaded %d cluster interpretations for run %s",
        len(rows),
        run_id,
    )

    result = {}
    for cluster, classification in rows:
        if isinstance(classification, str):
            classification = json.loads(classification)

        if isinstance(classification, dict):
            result[int(cluster)] = classification

    return result


def fetch_occurrences(
    conn,
    occurrence_ids: list[str],
    words: int,
    min_year: int | None = None,
    max_year: int | None = None,
) -> dict:
    """
    Fetch metadata and a token-window passage for each occurrence.

    The lateral subquery uses the occurrence's own hit_idx, rather than
    searching the passage for the surface form.
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
          AND (%s::int IS NULL OR o.pub_year >= %s::int)
          AND (%s::int IS NULL OR o.pub_year <= %s::int)
    """

    result = {}
    batch_size = 10_000

    with conn.cursor() as cur:
        for start in range(0, len(occurrence_ids), batch_size):
            batch = occurrence_ids[start:start + batch_size]
            cur.execute(
                sql,
                (
                    words,
                    words,
                    batch,
                    min_year,
                    min_year,
                    max_year,
                    max_year,
                ),
            )

            for row in cur.fetchall():
                (
                    oid,
                    corpus,
                    doc_id,
                    year,
                    hit_idx,
                    token,
                    author,
                    title,
                    passage,
                ) = row

                result[oid] = {
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "year": year,
                    "hit_idx": hit_idx,
                    "token": token or "",
                    "author": author or "Unknown author",
                    "title": title or doc_id,
                    "passage": passage or "",
                }

    return result


def build_cluster_traces(
    ids,
    xy,
    labels,
    probs,
    metadata: dict,
    interpretations: dict[int, dict],
    *,
    wrap_width: int = 60,
    point_size: float = 5.0,
    noise: bool = False,
) -> tuple[list[dict], list[list[str]]]:
    """
    Build JSON-compatible Plotly Scattergl trace dictionaries and the
    shared document lookup array.

    customdata layout:
      0 year text
      1 wrapped heading
      2 wrapped corpus/doc
      3 wrapped passage
      4 occurrence id
      5 membership probability
      6 numeric year
      7 index into docs
      8 hit_idx
    """
    from plotly.colors import qualitative

    ids = np.asarray(ids).astype(str)
    xy = np.asarray(xy)
    labels = np.asarray(labels).astype(int)
    probs = np.asarray(probs)

    if not (len(ids) == len(xy) == len(labels) == len(probs)):
        raise ValueError("The occurrence, coordinate, label and probability arrays must have equal lengths")

    palette = qualitative.Dark24
    traces: list[dict] = []

    # One entry per document, shared by all points.
    docs: list[dict[str, str]] = []
    doc_index: dict[tuple[str, str], int] = {}

    def doc_slot(m: dict) -> int:
        key = (m["corpus"], m["doc_id"])
        if key not in doc_index:
            doc_index[key] = len(docs)
            docs.append({
                "corpus": m["corpus"],
                "doc_id": m["doc_id"],
                "author": m["author"],
                "title": m["title"],
            })
        return doc_index[key]

    cluster_ids = sorted(c for c in set(labels.tolist()) if c >= 0)
    if noise and np.any(labels == -1):
        cluster_ids = [-1] + cluster_ids

    for cluster in cluster_ids:
        idx = np.flatnonzero(labels == cluster)
        if not len(idx):
            continue

        custom = []

        for i in idx:
            occurrence_id = ids[i]
            m = metadata.get(occurrence_id)
            if m is None:
                custom.append({
                    "yearText": "?",
                    "heading": "Unknown",
                    "source": "No metadata",
                    "passageHtml": "",
                    "occurrenceId": occurrence_id,
                    "membership": 0.0,
                    "year": None,
                    "docIndex": -1,
                    "hitIdx": None,
                })
                continue

            heading = f"{m['author']}, {m['title'][:100]}"
            passage = wrap_html(m["passage"], wrap_width)

            custom.append({
                "yearText": str(m["year"]) if m["year"] is not None else "Unknown",
                "heading": wrap_html(heading, wrap_width),
                "source": wrap_html(
                    f"{m['corpus']} / {m['doc_id']}",
                    wrap_width,
                ),
                "passageHtml": passage,
                "occurrenceId": occurrence_id,
                "membership": float(probs[i]),
                "year": int(m["year"]) if m["year"] is not None else None,
                "docIndex": doc_slot(m),
                "hitIdx": int(m["hit_idx"]) if m["hit_idx"] is not None else None,
            })

        is_noise = cluster == -1
        category = ""

        if is_noise:
            label = "Noise"
            colour = "#777777"
        else:
            interpretation = interpretations.get(cluster, {})
            category = interpretation.get("category", "").strip()
            label = (
                category
                if category
                else f"Cluster {cluster}"
            )
            colour = palette[cluster % len(palette)]

        traces.append({
            "type": "scattergl",
            "x": np.round(xy[idx, 0], 4).tolist(),
            "y": np.round(xy[idx, 1], 4).tolist(),
            "mode": "markers",
            "name": f"{label} (n={len(idx):,})",
            "meta": {
                "label": label,
                "cluster": int(cluster),
                "category": category,
            },
            "marker": {
                "size": 3 if is_noise else point_size,
                "color": colour,
                "opacity": 0.25 if is_noise else 0.78,
            },
            "customdata": custom,
            "hovertemplate": (
                "<b>%{customdata[1]}</b><br>"
                "%{customdata[0]}<br>"
                "<span style='color:#aaaaaa'>%{customdata[2]}</span><br><br>"
                "%{customdata[3]}<br><br>"
                "<span style='color:#aaaaaa'>"
                "Membership: %{customdata[5]:.2f}<br>"
                "Occurrence: %{customdata[4]}"
                "</span><extra></extra>"
            ),
        })

    return traces, docs

