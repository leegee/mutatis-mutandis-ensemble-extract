"""
passage_search_pipeline/texts.py

Postgres lookup of passage text and document metadata.

`fetch_passage_texts` resolves all hits in ONE query (instead of one query
per hit), which matters once this sits behind an API.
"""

from __future__ import annotations

from typing import Dict, List, Optional

_EMPTY = {"title": None, "author": None, "filepath": None, "passage_text": None}

_SQL = """
WITH req(ord, corpus, doc_id, tok_start, tok_end) AS (
    SELECT * FROM unnest(
        %s::bigint[], %s::text[], %s::text[], %s::bigint[], %s::bigint[]
    )
)
SELECT
    r.ord,
    d.title,
    d.author,
    d.filepath,
    string_agg(t.token, ' ' ORDER BY t.token_idx) AS passage_text
FROM req r
JOIN documents d
  ON d.corpus = r.corpus AND d.doc_id = r.doc_id
JOIN tokens t
  ON t.corpus = d.corpus
 AND t.doc_id = d.doc_id
 AND t.token_idx >= r.tok_start
 AND t.token_idx <  r.tok_end
GROUP BY r.ord, d.title, d.author, d.filepath
"""


def fetch_passage_texts(conn, results: List[dict]) -> List[Dict[str, Optional[str]]]:
    """
    Return one metadata dict per result, in the same order as `results`.
    Hits with no matching document/tokens get all-None fields.
    """
    if not results:
        return []

    params = (
        list(range(len(results))),
        [str(r["corpus"]) for r in results],
        [str(r["doc_id"]) for r in results],
        [int(r["token_start"]) for r in results],
        [int(r["token_end"]) for r in results],
    )

    with conn.cursor() as cur:
        cur.execute(_SQL, params)
        rows = cur.fetchall()

    out = [dict(_EMPTY) for _ in results]
    for ord_, title, author, filepath, text in rows:
        out[int(ord_)] = {
            "title": title,
            "author": author,
            "filepath": filepath,
            "passage_text": text,
        }
    return out


def fetch_passage_text(conn, result: dict) -> Dict[str, Optional[str]]:
    """Single-hit convenience wrapper (kept for older callers)."""
    return fetch_passage_texts(conn, [result])[0]
