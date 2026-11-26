
"""
11_export_tiny_target_windows.py

Postgres -> parquet. One row per hit occurrence: the hit's position, matched
token, term group(s), the route(s) that qualified it, and the +/-50-word
context around it. Input for 21_colab_embed_targets.py.

Routes are defined anywhere imported and re-exported in corpus_config.py.
This exporter retains route labels and hit occurrences, unlike the document
selector, which only needs to know which documents qualify.

    python 11_export_tiny_target_windows.py --count-only
    python 11_export_tiny_target_windows.py
"""

import argparse
from itertools import groupby

import pyarrow as pa
import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_storage import clear, local_dir, publish
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import (
    PROXIMITY,
    INCLUSION_ROUTES,
    DIRECT_INCLUSION_GROUPS,
    build_setup_sql,
    frequency_diagnostic_sql,
)

logger = get_logger("embed.export-targets")

SUBDIR = "source_hits"
SHARD_PREFIX = "hits_"
SHARD_GLOB = f"{SHARD_PREFIX}*.parquet"
OUT_DIR = local_dir(SUBDIR)

# Remove shards of a previous hit export (locally, and from the HF repo on publish).
CLEAR_BEFORE_EXPORT = True

TABLE = "tokens"
DOC_TABLE = "documents"

HITS_PER_SHARD = 5_000
WINDOW_LEFT = 50
WINDOW_RIGHT = 49

# Exclude a token matching itself across the two groups of a route.
# For example, a token belonging to both WHITE and APPEARANCE cannot qualify
# against itself, though it can still qualify against a different nearby token.
EXCLUDE_SELF_MATCH = True

SCHEMA = pa.schema([
    ("corpus", pa.string()),
    ("doc_id", pa.string()),
    ("pub_year", pa.int32()),
    ("hit_idx", pa.int32()),
    ("matched_token", pa.string()),
    ("hit_groups", pa.list_(pa.string())),
    ("routes", pa.list_(pa.string())),
    ("token_idx", pa.list_(pa.int32())),
    ("tokens", pa.list_(pa.string())),
])


def _route(label: str, hit_grp: str, partner_grp: str) -> str:
    """Build one occurrence-level proximity route."""
    not_self = "AND p.token_idx <> h.token_idx" if EXCLUDE_SELF_MATCH else ""

    return f"""
        SELECT h.corpus, h.doc_id, h.token_idx, h.grp,
               '{label}'::text AS route
        FROM target_tokens AS h
        JOIN target_tokens AS p
          ON p.corpus = h.corpus
         AND p.doc_id = h.doc_id
         AND p.grp = '{partner_grp}'
         AND p.token_idx BETWEEN h.token_idx - {PROXIMITY}
                             AND h.token_idx + {PROXIMITY}
         {not_self}
        WHERE h.grp = '{hit_grp}'
    """


def _direct_route(group: str) -> str:
    """Build a route for a group that qualifies without a proximity partner."""
    return f"""
        SELECT corpus, doc_id, token_idx, grp,
               '{group}'::text AS route
        FROM target_tokens
        WHERE grp = '{group}'
    """


def hit_occurrences_sql() -> str:
    """
    Build the occurrence-level hit table from the shared route declarations.

    Multiple routes qualifying the same token position are aggregated into
    one occurrence, retaining all route labels and hit groups.
    """
    route_queries = [
        _route(label, hit_grp, partner_grp)
        for label, hit_grp, partner_grp in INCLUSION_ROUTES
    ]

    route_queries.extend(
        _direct_route(group)
        for group in DIRECT_INCLUSION_GROUPS
    )

    if not route_queries:
        raise ValueError("No inclusion routes or direct inclusion groups defined")

    routes_sql = "\nUNION ALL\n".join(route_queries)

    return f"""
        DROP TABLE IF EXISTS hit_occurrences;

        CREATE TEMP TABLE hit_occurrences AS
        SELECT corpus, doc_id, token_idx,
               array_agg(DISTINCT route ORDER BY route) AS routes,
               array_agg(DISTINCT grp ORDER BY grp) AS grps
        FROM (
            {routes_sql}
        ) AS r
        GROUP BY corpus, doc_id, token_idx;

        CREATE INDEX ON hit_occurrences (corpus, doc_id, token_idx);
        ANALYZE hit_occurrences;
    """


def export_sql() -> str:
    return f"""
        SELECT h.corpus, h.doc_id, d.pub_year, h.token_idx AS hit_idx,
               h.grps, h.routes, t.token_idx, t.token
        FROM hit_occurrences AS h
        JOIN {TABLE} AS t
          ON t.corpus = h.corpus
         AND t.doc_id = h.doc_id
         AND t.token_idx BETWEEN h.token_idx - {WINDOW_LEFT}
                             AND h.token_idx + {WINDOW_RIGHT}
        JOIN {DOC_TABLE} AS d
          ON d.corpus = h.corpus
         AND d.doc_id = h.doc_id
        ORDER BY h.corpus, h.doc_id, h.token_idx, t.token_idx
    """


def flush(records: list[dict], shard_no: int) -> None:
    table = pa.Table.from_pylist(records, schema=SCHEMA)
    final = OUT_DIR / f"{SHARD_PREFIX}{shard_no:05d}.parquet"
    tmp = final.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(final)
    logger.info("Wrote %s (%d hits)", final, len(records))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Build the hit table, log counts, and stop without exporting.",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection(application_name="export-target-windows")

    try:
        with conn.cursor() as cur:
            setup_sql, setup_params = build_setup_sql(
                table=TABLE,
                inline=True,
            )
            cur.execute(setup_sql, setup_params)
            logger.info("Created vocab / term_expansion / target_tokens")

            cur.execute(frequency_diagnostic_sql())
            logger.info("Top expanded terms by frequency:")
            for grp, tok, n in cur.fetchall():
                logger.info("  %12d  %-12s  %s", n, grp, tok)

            cur.execute(hit_occurrences_sql())

            cur.execute("""
                SELECT count(*),
                       count(DISTINCT (corpus, doc_id))
                FROM hit_occurrences
            """)
            hits, docs = cur.fetchone()
            logger.info("%d hit occurrences in %d documents", hits, docs)

            cur.execute("""
                SELECT r, count(*)
                FROM hit_occurrences, unnest(routes) AS r
                GROUP BY r
                ORDER BY 2 DESC
            """)
            for route, n in cur.fetchall():
                logger.info("  route  %-24s %9d", route, n)

            cur.execute("""
                SELECT g, count(*)
                FROM hit_occurrences, unnest(grps) AS g
                GROUP BY g
                ORDER BY 2 DESC
            """)
            for grp, n in cur.fetchall():
                logger.info("  group  %-24s %9d", grp, n)

        conn.commit()

        if args.count_only:
            logger.info("--count-only: stopping before export")
            return

        if CLEAR_BEFORE_EXPORT:
            clear(SUBDIR, SHARD_GLOB)

        records: list[dict] = []
        shard_no = 0
        exported = 0
        rows_seen = 0
        skipped_no_year = 0

        with conn.cursor(name="export_target_windows") as cur:
            cur.itersize = 10_000
            cur.execute(export_sql())

            for (corpus, doc_id, hit_idx), grouped in groupby(
                cur,
                key=lambda row: (row[0], row[1], row[3]),
            ):
                rows = list(grouped)
                pub_year = rows[0][2]

                if pub_year is None:
                    skipped_no_year += 1
                    continue

                idxs = [row[6] for row in rows]
                toks = [row[7] for row in rows]

                try:
                    matched = toks[idxs.index(hit_idx)]
                except ValueError:
                    raise RuntimeError(
                        f"hit {hit_idx} missing from its own window: "
                        f"{corpus}/{doc_id}"
                    )

                records.append({
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "pub_year": pub_year,
                    "hit_idx": hit_idx,
                    "matched_token": matched,
                    "hit_groups": list(rows[0][4]),
                    "routes": list(rows[0][5]),
                    "token_idx": idxs,
                    "tokens": toks,
                })

                exported += 1
                rows_seen += len(rows)

                if len(records) >= HITS_PER_SHARD:
                    flush(records, shard_no)
                    records = []
                    shard_no += 1

                if exported % 10_000 == 0:
                    logger.info(
                        "Exported %d hits; %d token rows",
                        exported,
                        rows_seen,
                    )

            if records:
                flush(records, shard_no)

        publish(SUBDIR, SHARD_GLOB, prune=CLEAR_BEFORE_EXPORT)

        # Deliberately no reset_outputs() / warn_stale_outputs():
        # existing output-passages embeddings do not depend on these shards.
        logger.info(
            "Done: exported %d hits (%d token rows); "
            "%d skipped for missing pub_year",
            exported,
            rows_seen,
            skipped_no_year,
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
