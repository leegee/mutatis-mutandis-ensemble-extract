"""
lib/passage_db.py- Shared PostgreSQL helpers for sampling seed / baseline windows and phrases.

Used by mask-fillers, phrase mask-fillers, and the substitute-collocate
analysers. All SQL fragments are fixed (never built from user text).
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# Scope definitions
# ---------------------------------------------------------------------------

SCOPES = {
    "pamphlet": {
        "table": "pamphlet_corpus",
        "join": "d.corpus = t.corpus AND d.doc_id = t.doc_id",
        "where": "",
    },
    "all": {
        "table": "documents",
        "join": "d.doc_id = t.doc_id",
        "where": "AND (d.lang = 'eng' OR d.lang IS NULL)",
    },
}

# token: uses idx_tokens_token_lower.
# canonical: uses idx_tokens_canonical (exact match on lower-cased variants).
MATCH_SQL = {
    "token": "lower(t.token) = ANY(%(variants)s)",
    "canonical": "t.canonical = ANY(%(variants)s)",
}


# ---------------------------------------------------------------------------
# Hit sampling, meta
# ---------------------------------------------------------------------------

def fetch_doc_meta(conn, doc_ids):
    """Return {doc_id: {"corpus": …, "title": …, "pub_year": …}}"""
    if not doc_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, corpus, title, pub_year
            FROM documents
            WHERE doc_id = ANY(%s)
            """,
            (list(set(doc_ids)),),
        )
        return {
            row[0]: {
                "corpus": row[1] or "",
                "title": (row[2] or "")[:120],   # truncate for readability
                "pub_year": row[3],
            }
            for row in cur.fetchall()
        }

def fetch_hits(
    conn,
    scope: str,
    variants: set[str] | list[str],
    match: str,
    lo: int,
    hi: int,
    n: int,
    per_doc: int,
) -> tuple[list[tuple[str, int]], set[str]]:
    """
    Randomly sample up to *n* single-token occurrences in the scope's
    documents for years lo..hi, at most *per_doc* from any one document.

    Returns ([(doc_id, token_idx)], {surface forms seen}).
    """
    sc = SCOPES[scope]
    query = f"""
        WITH hits AS (
            SELECT t.doc_id, t.token_idx, lower(t.token) AS surface,
                   row_number() OVER (
                       PARTITION BY t.doc_id ORDER BY random()
                   ) AS rn
            FROM tokens t
            JOIN {sc['table']} d ON {sc['join']}
            WHERE {MATCH_SQL[match]}
              AND d.pub_year BETWEEN %(lo)s AND %(hi)s
              {sc['where']}
        )
        SELECT doc_id, token_idx, surface
        FROM hits
        WHERE rn <= %(per_doc)s
        ORDER BY random()
        LIMIT %(n)s
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            {
                "variants": sorted(variants),
                "lo": lo,
                "hi": hi,
                "per_doc": per_doc,
                "n": n,
            },
        )
        rows = cur.fetchall()
    return [(r[0], r[1]) for r in rows], {r[2] for r in rows}


def fetch_phrase_hits(
    conn,
    scope: str,
    slots: list[set[str]],
    match: str,
    lo: int,
    hi: int,
    n: int,
    per_doc: int,
    max_gap: int = 0,
) -> tuple[list[tuple[str, int, int]], set[str]]:
    """
    Like :func:`fetch_hits` for a phrase: one token per slot, in order, with
    at most *max_gap* other tokens between consecutive slots.

    Returns ([(doc_id, start_idx, end_idx)], {surface words seen}).
    """
    sc = SCOPES[scope]
    k = len(slots)

    def expr(alias: str) -> str:
        return f"lower({alias}.token)" if match == "token" else f"{alias}.canonical"

    aliases = ["t"] + [f"t{i}" for i in range(2, k + 1)]
    params: dict[str, Any] = {
        "lo": lo,
        "hi": hi,
        "per_doc": per_doc,
        "n": n,
        "gap": int(max_gap),
        "slot1": sorted(slots[0]),
    }
    joins = []
    for i in range(2, k + 1):
        a, prev = aliases[i - 1], aliases[i - 2]
        joins.append(
            f"JOIN tokens {a} ON {a}.doc_id = t.doc_id AND {a}.corpus = t.corpus "
            f"AND {a}.token_idx BETWEEN {prev}.token_idx + 1 "
            f"AND {prev}.token_idx + 1 + %(gap)s "
            f"AND {expr(a)} = ANY(%(slot{i})s)"
        )
        params[f"slot{i}"] = sorted(slots[i - 1])

    surface = " || ' ' || ".join(f"lower({a}.token)" for a in aliases)
    last = aliases[-1]
    query = f"""
        WITH spans AS (
            SELECT DISTINCT ON (t.doc_id, t.token_idx)
                   t.doc_id, t.token_idx, {last}.token_idx AS end_idx,
                   {surface} AS surface
            FROM tokens t
            JOIN {sc['table']} d ON {sc['join']}
            {' '.join(joins)}
            WHERE {expr('t')} = ANY(%(slot1)s)
              AND d.pub_year BETWEEN %(lo)s AND %(hi)s
              {sc['where']}
            ORDER BY t.doc_id, t.token_idx, {last}.token_idx
        ), hits AS (
            SELECT doc_id, token_idx, end_idx, surface,
                   row_number() OVER (
                       PARTITION BY doc_id ORDER BY random()
                   ) AS rn
            FROM spans
        )
        SELECT doc_id, token_idx, end_idx, surface
        FROM hits
        WHERE rn <= %(per_doc)s
        ORDER BY random()
        LIMIT %(n)s
    """
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    return (
        [(r[0], r[1], r[2]) for r in rows],
        {w for r in rows for w in r[3].split()},
    )


def fetch_doc_lengths(conn, doc_ids) -> dict[str, int]:
    """doc_id -> token_count, for matched baseline sampling."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, token_count FROM documents WHERE doc_id = ANY(%s)",
            (sorted(set(doc_ids)),),
        )
        return {d: tc for d, tc in cur.fetchall() if tc}


def matched_hits(
    seed_hits: list[tuple[str, int]],
    doc_len: dict[str, int],
    context: int,
    rng: random.Random,
    per_hit: int,
) -> list[tuple[str, int]]:
    """
    For each seed occurrence, pick up to *per_hit* baseline centres in
    the SAME document.

    Baseline windows must not overlap the seed window or any previously
    selected baseline window in that document.

    Windows are treated as inclusive intervals:
        [centre - context, centre + context]

    Returns fewer than requested controls when sampling is constrained.

    TODO:

    To guarantee non-overlap with all seed windows, prepopulate occupied with
    every seed window before sampling any controls.

    Sampling policy changes when a document is crowded. The function may return
    fewer controls than requested after 100 failed attempts. Should record the
    requested and achieved control counts so that baseline shortages are visible
    rather than silently ignored.
    """
    out: list[tuple[str, int]] = []
    occupied: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for doc, idx in seed_hits:
        tc = doc_len.get(doc)
        if not tc or tc <= 2 * context + 1:
            continue

        # Reserve the seed's context window so no control can overlap it.
        seed_lo = max(0, idx - context)
        seed_hi = min(tc - 1, idx + context)

        # Seed windows may overlap one another; record each exclusion.
        occupied[doc].append((seed_lo, seed_hi))

        for _ in range(per_hit):
            for _try in range(100):
                c = rng.randint(context, tc - context - 1)
                lo, hi = c - context, c + context

                # Inclusive intervals overlap unless one ends before
                # the other begins.
                if any(
                    not (hi < old_lo or lo > old_hi)
                    for old_lo, old_hi in occupied[doc]
                ):
                    continue

                out.append((doc, c))
                occupied[doc].append((lo, hi))
                break

    return out


def fetch_random_hits(
    conn,
    scope: str,
    lo: int,
    hi: int,
    n: int,
    context: int,
    rng: random.Random,
) -> list[tuple[str, int]]:
    """
    Random (doc_id, token_idx) centres from the whole period
    (``--baseline period`` mode). Documents are drawn with replacement,
    weighted by length (capped so a few huge texts cannot dominate).
    """
    sc = SCOPES[scope]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT d.doc_id, d.token_count
            FROM {sc['table']} d
            WHERE d.pub_year BETWEEN %s AND %s
              AND d.token_count > %s
              {sc['where']}
            """,
            (lo, hi, 2 * context + 1),
        )
        docs = cur.fetchall()
    if not docs:
        return []
    picked = rng.choices(
        docs, weights=[min(tc, 50_000) for _, tc in docs], k=n
    )
    return [(d, rng.randint(context, tc - context - 1)) for d, tc in picked]


# ---------------------------------------------------------------------------
# Window materialisation
# ---------------------------------------------------------------------------

WINDOW_SQL = """
    SELECT w.ord, t.token_idx, t.token
    FROM unnest(%s::int[], %s::text[], %s::int[], %s::int[])
         AS w(ord, doc_id, lo, hi)
    JOIN tokens t
      ON t.doc_id = w.doc_id
     AND t.token_idx BETWEEN w.lo AND w.hi
    ORDER BY w.ord, t.token_idx
"""


def fetch_windows(
    conn,
    hits: list[tuple],
    context: int,
    batch: int = 200,
) -> list[tuple]:
    """
    Context windows (*context* tokens either side) around each hit.

    *hits* may be ``(doc_id, token_idx)`` or ``(doc_id, start_idx, end_idx)``.
    Returns ``[(hit, token_idxs, words)]`` in hit order.
    """
    out: list[tuple] = []
    for off in range(0, len(hits), batch):
        chunk = hits[off : off + batch]
        by_ord: dict[int, list] = defaultdict(list)
        with conn.cursor() as cur:
            cur.execute(
                WINDOW_SQL,
                (
                    list(range(len(chunk))),
                    [h[0] for h in chunk],
                    [max(0, h[1] - context) for h in chunk],
                    [h[1] + context for h in chunk],
                ),
            )
            for o, idx, tok in cur.fetchall():
                by_ord[o].append((idx, tok))

        for o, hit in enumerate(chunk):
            rows = by_ord.get(o)
            if not rows:
                continue
            idxs = [r[0] for r in rows]
            words = [r[1] if r[1].strip() else "." for r in rows]
            out.append((hit, idxs, words))
    return out


def windows_to_passages(
    windows: list[tuple],
) -> tuple[list[dict], list[tuple[int, int]]]:
    """
    Convert raw windows into passage dicts plus occurrence indices.

    Phrase hits carry an end index (``hit[2]``); single-token hits do not.
    Each passage records ``span = (w_idx, e_idx)`` so downstream code can
    mask the whole phrase.
    """
    passages: list[dict] = []
    occ: list[tuple[int, int]] = []
    for hit, idxs, words in windows:
        doc_id, tidx = hit[0], hit[1]
        end = hit[2] if len(hit) > 2 else tidx
        try:
            w_idx = idxs.index(tidx)
            e_idx = idxs.index(end)
        except ValueError:
            continue
        passages.append(
            {
                "doc_id": doc_id,
                "word_start": idxs[0],
                "words": words,
                "hit": (doc_id, tidx),
                "span": (w_idx, e_idx),
            }
        )
        occ.append((len(passages) - 1, w_idx))
    return passages, occ


# ---------------------------------------------------------------------------
# Baseline position helpers (used by both single-word and phrase scripts)
# ---------------------------------------------------------------------------

def random_positions(
    passages: list[dict],
    excl_keys: set[str],
    n: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Random content-word positions pooled over all passages (csv mode)."""
    from mutatis_mutandis.lib.passage_stem import content_word  # local to avoid cycles

    pool = [
        (p_idx, w_idx)
        for p_idx, p in enumerate(passages)
        for w_idx, w in enumerate(p["words"])
        if content_word(w, excl_keys)
    ]
    rng.shuffle(pool)
    return pool[:n]


def one_position_per_passage(
    passages: list[dict],
    excl_keys: set[str],
    rng: random.Random,
) -> list[tuple[int, int]]:
    """One random content word per baseline window (db modes)."""
    from mutatis_mutandis.lib.passage_stem import content_word

    out: list[tuple[int, int]] = []
    for p_idx, p in enumerate(passages):
        cand = [
            i
            for i, w in enumerate(p["words"])
            if content_word(w, excl_keys)
        ]
        if cand:
            out.append((p_idx, rng.choice(cand)))
    return out
