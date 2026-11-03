
"""
passages_1_export_windows.py

As `passages_1_export_full.py` but exports sparse token windows around qualifying historical albinism targets.

NB currently makes no use of the corpus SQL used in `passages_1_export_full.py`.

Storage backend (Google Drive or Hugging Face) is chosen by the PASSAGES_STORAGE
environment variable; see lib/corpus_storage.py.
"""

from collections import defaultdict
from itertools import groupby
from pathlib import Path

import lancedb
import pyarrow as pa
import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, build_export_query
from mutatis_mutandis.lib.corpus_logging import logger
from mutatis_mutandis.lib.corpus_storage import clear, local_dir, publish, reset_outputs, warn_stale_outputs

PARQ_OUTPUT_DIR = local_dir("source_tokens")
SHARD_PREFIX = 'tokens_'
SHARD_GLOB = f"{SHARD_PREFIX}*.parquet"
# Remove shards of any previous batch (locally, and from the HF repo on publish)
# so stale shards never mix with the new export.
CLEAR_BEFORE_EXPORT = True
# New tokens invalidate the embeddings built from the old ones, and the Colab job
# skips shards that already have output. Delete embeddings + checkpoints (locally
# and in the HF repo) after a successful publish. Set False to only get a warning.
CLEAR_OUTPUTS_ON_EXPORT = True

FORCE_EXPORT_DOC_IDS = {
#     "albinism_case_report_psaila_1972",
}

DOC_TABLE = "documents"
TABLE = "tokens"

DOCS_PER_SHARD = 10
WINDOW_WORDS = 100
WINDOW_LEFT = WINDOW_WORDS // 2
WINDOW_RIGHT = WINDOW_WORDS - WINDOW_LEFT - 1

SCHEMA = pa.schema([
    ("corpus", pa.string()),
    ("doc_id", pa.string()),
    ("pub_year", pa.int32()),
    ("token_idx", pa.list_(pa.int32())),
    ("tokens", pa.list_(pa.string())),
])


def flush(docs: list[dict], shard_no: int) -> None:
    table = pa.Table.from_pylist(docs, schema=SCHEMA)
    final = PARQ_OUTPUT_DIR / f"{SHARD_PREFIX}_{shard_no:05d}.parquet"
    tmp = final.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(final)
    logger.info("Wrote %s (%d documents)", final, len(docs))


def indexed_documents() -> set[tuple[str, str]]:
    """Collect document identities present in any passage representation."""
    db = lancedb.connect(str(LANCE_INDEXES_DIR))
    names = db.list_tables().tables
    indexed: set[tuple[str, str]] = set()

    for name in names:
        if not name.startswith((
            "passage_l8__",
            "passage_last__",
            "passage_mean4__",
        )):
            continue

        table = db.open_table(name)
        rows = table.search().select(["corpus", "doc_id"]).to_arrow()
        indexed.update(zip(
            rows["corpus"].to_pylist(),
            rows["doc_id"].to_pylist(),
        ))

    logger.info(
        "Found %d indexed documents across %d Lance tables",
        len(indexed), len(names),
    )
    return indexed


def populate_indexed_docs(conn, indexed: set[tuple[str, str]]) -> None:
    logger.info("Enter populate_indexed_docs with %d", len(indexed))
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE export_indexed_docs (
                corpus text NOT NULL,
                doc_id text NOT NULL,
                PRIMARY KEY (corpus, doc_id)
            ) ON COMMIT PRESERVE ROWS
        """)

        ordered = sorted(indexed)
        for offset in range(0, len(ordered), 5000):
            cur.executemany(
                """
                INSERT INTO export_indexed_docs (corpus, doc_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                ordered[offset:offset + 5000],
            )

    conn.commit()
    logger.info("Leave populate_indexed_docs")


def main() -> None:
    indexed = indexed_documents()
    conn = get_connection(application_name="export-token-windows")

    try:
        populate_indexed_docs(conn, indexed)
        if CLEAR_BEFORE_EXPORT:
            clear("source_tokens", SHARD_GLOB)
        sql, params = build_export_query(TABLE, DOC_TABLE, WINDOW_LEFT, WINDOW_RIGHT)
        params.extend([sorted(FORCE_EXPORT_DOC_IDS)])
        docs: list[dict] = []
        shard_no = 0
        exported = 0
        rows_seen = 0

        logger.info("Itterate over export docs")
        with conn.cursor(name="export_tokens") as cur:
            cur.itersize = 10_000
            cur.execute(sql, params)

            for (corpus, doc_id), grouped_rows in groupby(
                cur,
                key=lambda row: (row[0], row[1]),
            ):
                rows = list(grouped_rows)
                docs.append({
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "pub_year": rows[0][2],
                    "token_idx": [row[3] for row in rows],
                    "tokens": [row[4] for row in rows],
                })

                exported += 1
                rows_seen += len(rows)

                if len(docs) >= DOCS_PER_SHARD:
                    flush(docs, shard_no)
                    docs = []
                    shard_no += 1

                if exported % 100 == 0:
                    logger.info( "Exported %d documents; %d token rows", exported, rows_seen, )

            if docs:
                flush(docs, shard_no)

        publish("source_tokens", SHARD_GLOB, prune=CLEAR_BEFORE_EXPORT)
        if CLEAR_OUTPUTS_ON_EXPORT:
            reset_outputs()
        else:
            warn_stale_outputs()
        logger.info( "Done: exported %d documents and %d token rows", exported, rows_seen, )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
