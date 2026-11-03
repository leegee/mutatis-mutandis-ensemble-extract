"""
passages_1_export_full.py

Exports one row per document (corpus, doc_id, pub_year, token_idx[], tokens[])
into parquet shards of DOCS_PER_SHARD documents.

Storage backend (Google Drive or Hugging Face) is chosen by the PASSAGES_STORAGE
environment variable; see lib/corpus_storage.py. On the hf backend the finished
shards are uploaded automatically at the end of the run.
"""
from itertools import groupby
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_storage import clear, local_dir, publish, reset_outputs, warn_stale_outputs

from mutatis_mutandis.lib.corpus_albinism import CORPUS_SQL

logger = get_logger('embed.export-full')

# Output directory (Drive folder or local staging folder, depending on backend)
EMB_OUTPUT_DIR = local_dir("source_tokens")

# PostgreSQL tables
DOC_TABLE = "documents"
TABLE = "tokens"

DOCS_PER_SHARD = 10 # 500

SHARD_GLOB = "tokens_*.parquet"
# Remove shards of any previous batch (locally, and from the HF repo on publish)
# so stale shards never mix with the new export.
CLEAR_BEFORE_EXPORT = True
# New tokens invalidate the embeddings built from the old ones, and the Colab job
# skips shards that already have output. Delete embeddings + checkpoints (locally
# and in the HF repo) after a successful publish. Set False to only get a warning.
CLEAR_OUTPUTS_ON_EXPORT = True

SCHEMA = pa.schema([
    ("corpus", pa.string()),
    ("doc_id", pa.string()),
    ("pub_year", pa.int32()),
    ("token_idx", pa.list_(pa.int32())),
    ("tokens", pa.list_(pa.string())),
])


def flush(docs: list[dict], shard_no: int) -> None:
    table = pa.Table.from_pylist(docs, schema=SCHEMA)
    final = EMB_OUTPUT_DIR / f"tokens_{shard_no:05d}.parquet"
    tmp = final.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(final)
    logger.info(f"wrote {final} ({len(docs)} docs)")


def main() -> None:
    conn = get_connection(application_name="export-tokens")

    if CLEAR_BEFORE_EXPORT:
        clear("source_tokens", SHARD_GLOB)

    with conn.cursor(name="export_tokens") as cur:
        cur.itersize = 100_000
        cur.execute(
            f"""
            WITH selected_docs AS (
                {CORPUS_SQL}
            )
            SELECT
                t.corpus,
                t.doc_id,
                d.pub_year,
                t.token_idx,
                t.token
            FROM {TABLE} AS t
            JOIN {DOC_TABLE} AS d
            ON d.corpus = t.corpus
            AND d.doc_id = t.doc_id
            JOIN selected_docs AS s
            ON s.corpus = t.corpus
            AND s.doc_id = t.doc_id
            ORDER BY t.corpus, t.doc_id, t.token_idx
            """
        )

        docs: list[dict] = []
        shard_no = 0

        for (corpus, doc_id), rows in groupby(cur, key=lambda r: (r[0], r[1])):
            logger.info(f"Do {doc_id}")
            rows = list(rows)
            docs.append({
                "corpus": corpus,
                "doc_id": doc_id,
                "pub_year": rows[0][2],
                "token_idx": [r[3] for r in rows],
                "tokens": [r[4] for r in rows],
            })

            if len(docs) >= DOCS_PER_SHARD:
                flush(docs, shard_no)
                docs, shard_no = [], shard_no + 1

        if docs:
            flush(docs, shard_no)

    conn.close()
    publish("source_tokens", SHARD_GLOB, prune=CLEAR_BEFORE_EXPORT)
    if CLEAR_OUTPUTS_ON_EXPORT:
        reset_outputs()
    else:
        warn_stale_outputs()
    logger.info("Done")


if __name__ == "__main__":
    main()
