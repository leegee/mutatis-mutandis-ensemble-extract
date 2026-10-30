"""
passage_search_pipeline/text_search.py

Keyword / phrase search over the Postgres `tokens` + `documents` tables.

Finds consecutive token sequences that match the query (case-insensitive),
expands each match to a window of surrounding tokens, and returns hits in
roughly the same shape as vector search (so the UI can reuse cards).

Year filtering uses documents.pub_year when the column is present; if your
schema lacks it, pass start_year=0 and end_year=2030 and the filter is a
no-op only if the column exists — see the SQL below.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Sequence

# Match the same tokenisation spirit as the UI highlight helper.
_TOKEN_RE = re.compile(r"[a-zA-Z\u00c0-\u024f']+", re.UNICODE)

_EMPTY = {
    "title": None,
    "author": None,
    "filepath": None,
    "passage_text": None,
    "pub_year": None,
}


def query_terms(query: str, min_len: int = 2) -> List[str]:
    """Lowercased content words from the user query."""
    return [t for t in _TOKEN_RE.findall(query.lower()) if len(t) >= min_len]


def span_passage_id(corpus: str, doc_id: str, token_start: int, token_end: int) -> str:
    """Stable 64-char hex id for a text-search span (not a Lance passage_id)."""
    key = f"text:{corpus}:{doc_id}:{token_start}:{token_end}".encode()
    return hashlib.sha256(key).hexdigest()


def _phrase_sql(n_terms: int, with_year: bool) -> str:
    """
    Build a query that finds consecutive tokens matching all terms in order.

    Parameters are bound in order:
      term_0, term_1, … term_{n-1}
      [start_year, end_year] if with_year
      limit
    """
    # t0 is the anchor; t1..t{n-1} join on consecutive token_idx.
    joins = []
    wheres = ["lower(t0.token) = %s"]
    for i in range(1, n_terms):
        joins.append(
            f"""
            JOIN tokens t{i}
              ON t{i}.corpus = t0.corpus
             AND t{i}.doc_id = t0.doc_id
             AND t{i}.token_idx = t0.token_idx + {i}
            """
        )
        wheres.append(f"lower(t{i}.token) = %s")

    year_join = ""
    year_where = ""
    if with_year:
        year_join = """
            JOIN documents d
              ON d.corpus = t0.corpus AND d.doc_id = t0.doc_id
        """
        year_where = "AND d.pub_year >= %s AND d.pub_year <= %s"

    join_sql = "\n".join(joins)
    where_sql = " AND ".join(wheres)

    # token_start / token_end are exclusive-end style to match vector hits.
    return f"""
        SELECT
            t0.corpus,
            t0.doc_id,
            t0.token_idx AS match_start,
            t0.token_idx + {n_terms} AS match_end
        FROM tokens t0
        {join_sql}
        {year_join}
        WHERE {where_sql}
        {year_where}
        ORDER BY t0.corpus, t0.doc_id, t0.token_idx
        LIMIT %s
    """


_META_SQL = """
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
    d.pub_year,
    string_agg(t.token, ' ' ORDER BY t.token_idx) AS passage_text
FROM req r
LEFT JOIN documents d
  ON d.corpus = r.corpus AND d.doc_id = r.doc_id
LEFT JOIN tokens t
  ON t.corpus = r.corpus
 AND t.doc_id = r.doc_id
 AND t.token_idx >= r.tok_start
 AND t.token_idx <  r.tok_end
GROUP BY r.ord, d.title, d.author, d.filepath, d.pub_year
"""


def search_text_passages(
    conn,
    query: str,
    *,
    limit: int = 30,
    start_year: int = 0,
    end_year: int = 2030,
    window_tokens: int = 40,
    use_year_filter: bool = True,
) -> List[dict]:
    """
    Return up to `limit` phrase matches expanded by ±window_tokens.

    Each result dict has:
      passage_id, corpus, doc_id, pub_year, token_start, token_end,
      title, author, filepath, text, match_start, match_end
    """
    terms = query_terms(query)
    if not terms:
        return []

    n = len(terms)
    # Cap phrase length so the dynamic JOIN stays reasonable.
    if n > 12:
        terms = terms[:12]
        n = 12

    sql = _phrase_sql(n, with_year=use_year_filter)
    params: list = list(terms)
    if use_year_filter:
        params.extend([int(start_year), int(end_year)])
    params.append(int(limit))

    with conn.cursor() as cur:
        try:
            cur.execute(sql, params)
            matches = cur.fetchall()
        except Exception:
            if not use_year_filter:
                raise
            # Retry without year filter.
            sql = _phrase_sql(n, with_year=False)
            params = list(terms) + [int(limit)]
            cur.execute(sql, params)
            matches = cur.fetchall()

    if not matches:
        return []

    # Expand windows and de-dupe overlapping spans in the same doc.
    windows = []
    seen = set()
    for corpus, doc_id, match_start, match_end in matches:
        tok_start = max(0, int(match_start) - window_tokens)
        tok_end = int(match_end) + window_tokens
        key = (corpus, doc_id, tok_start, tok_end)
        if key in seen:
            continue
        seen.add(key)
        windows.append(
            {
                "corpus": str(corpus),
                "doc_id": str(doc_id),
                "match_start": int(match_start),
                "match_end": int(match_end),
                "token_start": tok_start,
                "token_end": tok_end,
            }
        )

    if not windows:
        return []

    meta_params = (
        list(range(len(windows))),
        [w["corpus"] for w in windows],
        [w["doc_id"] for w in windows],
        [w["token_start"] for w in windows],
        [w["token_end"] for w in windows],
    )

    with conn.cursor() as cur:
        cur.execute(_META_SQL, meta_params)
        rows = cur.fetchall()

    by_ord: Dict[int, dict] = {}
    for ord_, title, author, filepath, pub_year, text in rows:
        by_ord[int(ord_)] = {
            "title": title,
            "author": author,
            "filepath": filepath,
            "pub_year": pub_year,
            "passage_text": text,
        }

    results = []
    for i, w in enumerate(windows):
        meta = by_ord.get(i, _EMPTY)
        year = meta.get("pub_year")
        # If year filter was applied in SQL, rows already match; if we fell
        # back, filter here when year is known.
        if year is not None and use_year_filter:
            if int(year) < start_year or int(year) > end_year:
                continue
        results.append(
            {
                "passage_id": span_passage_id(
                    w["corpus"], w["doc_id"], w["token_start"], w["token_end"]
                ),
                "corpus": w["corpus"],
                "doc_id": w["doc_id"],
                "pub_year": int(year) if year is not None else 0,
                "token_start": w["token_start"],
                "token_end": w["token_end"],
                "match_start": w["match_start"],
                "match_end": w["match_end"],
                "word_start": None,
                "word_end": None,
                "title": meta.get("title"),
                "author": meta.get("author"),
                "filepath": meta.get("filepath"),
                "text": meta.get("passage_text"),
                # No vector distance; UI treats missing score/distance as text hit.
                "distance": 0.0,
                "score": None,
                "sim_q": None,
                "sim_neg": None,
            }
        )
    return results[:limit]
