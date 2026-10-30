#!/usr/bin/env python

"""
passages_3_passages_parquet_to_lance.py
"""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_config import (
    LANCE_INDEXES_DIR,
    LANCE_BUCKET_SIZE,
    LANCE_MODEL_NAME,
    MAPPED_GOOGLE_DRIVE,
    PASSAGE_SCALES,
)
from mutatis_mutandis.lib.corpus_logging import logger


# INPUT_DIR = MAPPED_GOOGLE_DRIVE / "output-passages"
INPUT_DIR = path = Path("D:/") / "temp" / "output-passages"

REPRESENTATIONS = ("l8", "last", "mean4")
VECTOR_DIM = 768

WRITE_BATCH_SIZE = 512
READ_BATCH_SIZE = 256

BUILD_INDEXES = True

VECTOR_INDEX_TYPE = "IVF_FLAT"
VECTOR_INDEX_METRIC = "cosine"

MIN_VECTOR_INDEX_PARTITIONS = 1
MAX_VECTOR_INDEX_PARTITIONS = 256

EXPECTED_INDEXES = {
    "vector_idx",
    "passage_id_idx",
    "pub_year_idx",
    "scale_idx",
}

logger.info("From INPUT_DIR:         %s", INPUT_DIR)
logger.info("To   LANCE_INDEXES_DIR: %s", LANCE_INDEXES_DIR)

# ---------------------------------------------------------------------------
# Shared indexing helpers
# ---------------------------------------------------------------------------

def year_bucket(
    year: int,
    bucket_size: int,
) -> tuple[int, int]:
    """Return the inclusive year range containing year."""
    start = (year // bucket_size) * bucket_size
    return start, start + bucket_size - 1


def vector_index_partitions(row_count: int) -> int:
    """
    Choose an IVF partition count based on the actual table size.

    Square-root scaling provides a reasonable starting heuristic,
    bounded to avoid excessive partitions for large tables and
    unsupported partitions for small tables.
    """
    if row_count <= 0:
        raise ValueError("row_count must be positive")

    return max(
        MIN_VECTOR_INDEX_PARTITIONS,
        min(
            MAX_VECTOR_INDEX_PARTITIONS,
            int(row_count ** 0.5),
        ),
    )


# ---------------------------------------------------------------------------
# Passage identity and table naming
# ---------------------------------------------------------------------------

def passage_id(
    corpus: str,
    doc_id: str,
    scale: str,
    word_start: int,
    word_end: int,
    token_start: int,
    token_end: int,
    *,
    source: str = "multi_scale_char_v1",
) -> str:
    """
    Deterministic passage identity.

    Scale is part of the identity because the same document can
    contain overlapping local, medium and broad passages.
    """
    identity = (
        f"{source}\0{corpus}\0{doc_id}\0{scale}\0"
        f"{word_start}\0{word_end}\0"
        f"{token_start}\0{token_end}"
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


def table_name(
    representation: str,
    pub_year: int,
) -> str:
    """
    One table per embedding representation and publication-year bucket.

    Scale remains a row-level field so all passage scales can be
    searched together or filtered independently.
    """
    start, end = year_bucket(
        pub_year,
        LANCE_BUCKET_SIZE,
    )

    return (
        f"passage_{representation}__{LANCE_MODEL_NAME}"
        f"__{start:04d}_{end:04d}"
    )


# ---------------------------------------------------------------------------
# Arrow schema
# ---------------------------------------------------------------------------

def make_schema() -> pa.Schema:
    return pa.schema([
        pa.field("passage_id", pa.string()),
        pa.field("corpus", pa.string()),
        pa.field("doc_id", pa.string()),
        pa.field("pub_year", pa.int32()),
        pa.field("scale", pa.string()),
        pa.field("char_start", pa.int32()),
        pa.field("char_end", pa.int32()),
        pa.field("word_start", pa.int32()),
        pa.field("word_end", pa.int32()),
        pa.field("token_start", pa.int32()),
        pa.field("token_end", pa.int32()),
        pa.field("embedding_model", pa.string()),
        pa.field(
            "vector",
            pa.list_(pa.float32(), VECTOR_DIM),
        ),
    ])


# ---------------------------------------------------------------------------
# Lance passage writer
# ---------------------------------------------------------------------------

class PassageWriter:
    """
    Idempotent writer for passage vectors.

    Each representation has its own set of year-bucketed tables.
    Passage provenance is retained in Lance alongside the vector,
    allowing retrieval without an immediate PostgreSQL join.
    """

    def __init__(self, root: Path) -> None:
        self.db = lancedb.connect(str(root))
        self.schema = make_schema()
        self.tables = {}

    def get_table(self, name: str):
        if name in self.tables:
            return self.tables[name]

        existing = set(self.db.list_tables().tables)

        if name in existing:
            table = self.db.open_table(name)
            self.validate_schema(table, name)
        else:
            logger.info(
                "[passages] creating Lance table %s",
                name,
            )
            table = self.db.create_table(
                name,
                schema=self.schema,
            )

        self.tables[name] = table
        return table

    def validate_schema(self, table, name: str) -> None:
        """
        Fail early if an existing table is incompatible.

        Extra columns are permitted, but all expected columns and
        their Arrow types must be present.
        """
        actual = table.schema
        actual_names = set(actual.names)

        missing = set(self.schema.names) - actual_names

        if missing:
            raise ValueError(
                f"[passages] table {name} has an incompatible schema; "
                f"missing columns: {sorted(missing)}. "
                "Drop and re-import the table if appropriate."
            )

        mismatched = []

        for expected_field in self.schema:
            actual_type = actual.field(
                expected_field.name
            ).type

            if actual_type != expected_field.type:
                mismatched.append(
                    (
                        expected_field.name,
                        str(actual_type),
                        str(expected_field.type),
                    )
                )

        if mismatched:
            raise ValueError(
                f"[passages] table {name} has incompatible field types: "
                f"{mismatched}"
            )

    @staticmethod
    def existing_ids(
        table,
        ids: set[str],
    ) -> set[str]:
        """Find passage IDs already present in a Lance table."""
        if not ids or table.count_rows() == 0:
            return set()

        found = set()
        ordered = sorted(ids)

        # SHA-256 hexadecimal IDs are safe in this predicate.
        for i in range(0, len(ordered), 500):
            chunk = ordered[i:i + 500]
            quoted = ",".join(
                f"'{value}'" for value in chunk
            )

            result = (
                table.search()
                .where(f"passage_id IN ({quoted})")
                .select(["passage_id"])
                .limit(len(chunk))
                .to_arrow()
            )

            found.update(
                result.column("passage_id").to_pylist()
            )

        return found

    def write(
        self,
        name: str,
        rows: list[dict],
    ) -> int:
        """
        Append new passage vectors, skipping existing identities.

        Also deduplicates within the incoming batch.
        """
        if not rows:
            return 0

        table = self.get_table(name)

        ids = {
            row["passage_id"]
            for row in rows
        }

        existing = self.existing_ids(table, ids)

        seen = set(existing)
        new_rows = []

        for row in rows:
            pid = row["passage_id"]

            if pid in seen:
                continue

            seen.add(pid)
            new_rows.append(row)

        if new_rows:
            table.add(
                new_rows,
                mode="append",
            )

        return len(new_rows)

    # -----------------------------------------------------------------------
    # Index management
    # -----------------------------------------------------------------------

    @staticmethod
    def index_is_complete(
        indexes: dict,
        name: str,
    ) -> bool:
        index = indexes.get(name)

        return (
            index is not None
            and index.num_unindexed_rows == 0
        )

    def build_indexes(self) -> None:
        """
        Build or repair indexes independently.

        Existing complete indexes are retained. Missing or incomplete
        indexes are created/replaced without unnecessarily rebuilding
        the other indexes.
        """
        for name, table in self.tables.items():
            row_count = table.count_rows()

            if row_count == 0:
                continue

            indexes = {
                index.name: index
                for index in table.list_indices()
            }

            # Vector index.
            if not self.index_is_complete(
                indexes,
                "vector_idx",
            ):
                partitions = vector_index_partitions(
                    row_count
                )

                logger.info(
                    "[passages] building vector index for %s: "
                    "%d rows, %d partitions",
                    name,
                    row_count,
                    partitions,
                )

                table.create_index(
                    metric=VECTOR_INDEX_METRIC,
                    index_type=VECTOR_INDEX_TYPE,
                    vector_column_name="vector",
                    num_partitions=partitions,
                    replace=True,
                )

            # Refresh the index list after vector index creation.
            indexes = {
                index.name: index
                for index in table.list_indices()
            }

            # Scalar indexes.
            for column in (
                "passage_id",
                "pub_year",
                "scale",
            ):
                index_name = f"{column}_idx"

                if self.index_is_complete(
                    indexes,
                    index_name,
                ):
                    continue

                logger.info(
                    "[passages] building scalar index %s for %s",
                    index_name,
                    name,
                )

                table.create_scalar_index(
                    column,
                    index_type="BTREE",
                    replace=True,
                )

                # Refresh so subsequent checks use current state.
                indexes = {
                    index.name: index
                    for index in table.list_indices()
                }

            # Final completeness diagnostic.
            indexes = {
                index.name: index
                for index in table.list_indices()
            }

            incomplete = (
                EXPECTED_INDEXES
                - {
                    index_name
                    for index_name in EXPECTED_INDEXES
                    if self.index_is_complete(
                        indexes,
                        index_name,
                    )
                }
            )

            if incomplete:
                logger.warning(
                    "[passages] indexes still incomplete for %s: %s",
                    name,
                    sorted(incomplete),
                )
            else:
                logger.info(
                    "[passages] all indexes complete for %s "
                    "(%d rows)",
                    name,
                    row_count,
                )


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def flush_buffers(
    writer: PassageWriter,
    buffers: dict,
) -> int:
    written = 0

    for name, rows in list(buffers.items()):
        if rows:
            written += writer.write(name, rows)
            buffers[name] = []

    return written


def import_shard(
    path: Path,
    writer: PassageWriter,
    *,
    legacy_ids: bool = False,
) -> tuple[int, int]:

    parquet = pq.ParquetFile(path)

    required = {
        "corpus",
        "doc_id",
        "pub_year",
        "scale",
        "char_start",
        "char_end",
        "word_start",
        "word_end",
        "token_start",
        "token_end",
        *(
            f"vec_{name}"
            for name in REPRESENTATIONS
        ),
    }

    missing = required - set(
        parquet.schema_arrow.names
    )

    if missing:
        raise ValueError(
            f"{path.name}: missing columns: "
            f"{sorted(missing)}"
        )

    buffers = defaultdict(list)

    passages_seen = 0
    rows_written = 0
    next_log = 10_000

    for batch in parquet.iter_batches(
        batch_size=READ_BATCH_SIZE
    ):

        # Validate all representations in bulk.
        for rep in REPRESENTATIONS:
            arr = batch.column(
                f"vec_{rep}"
            )

            vec = arr.values.to_numpy(
                zero_copy_only=False
            ).reshape(-1, VECTOR_DIM)

            bad = (
                ~np.isfinite(vec).all(axis=1)
                | (np.abs(vec).sum(axis=1) == 0)
            )

            if bad.any():
                bad_rows = np.flatnonzero(bad)

                raise ValueError(
                    f"{path.name}: {len(bad_rows)} invalid "
                    f"{rep} vectors in batch; "
                    f"batch row offsets="
                    f"{bad_rows[:10].tolist()}"
                )

        for row in batch.to_pylist():
            passages_seen += 1

            year = row["pub_year"]

            if year is None:
                raise ValueError(
                    f"{path.name}: passage has no publication "
                    f"year; doc_id={row['doc_id']!r}"
                )

            start = int(row["word_start"])
            end = int(row["word_end"])

            if end <= start:
                raise ValueError(
                    f"{path.name}: invalid passage span "
                    f"{start}:{end}"
                )

            scale = row["scale"]

            if scale not in PASSAGE_SCALES:
                raise ValueError(
                    f"{path.name}: unexpected scale {scale!r}"
                )

            token_start = int(row["token_start"])
            token_end = int(row["token_end"])

            if token_end <= token_start:
                raise ValueError(
                    f"{path.name}: invalid token span "
                    f"{token_start}:{token_end}"
                )

            if legacy_ids:
                pid = passage_id(
                    row["corpus"],
                    row["doc_id"],
                    scale="legacy",
                    word_start=start,
                    word_end=end,
                    token_start=token_start,
                    token_end=token_end,
                    source="full_text_v1",
                )
            else:
                pid = passage_id(
                    row["corpus"],
                    row["doc_id"],
                    scale=scale,
                    word_start=start,
                    word_end=end,
                    token_start=token_start,
                    token_end=token_end,
                    source="multi_scale_char_v1",
                )

            common = {
                "passage_id": pid,
                "corpus": row["corpus"],
                "doc_id": row["doc_id"],
                "pub_year": int(year),
                "scale": scale,
                "char_start": int(row["char_start"]),
                "char_end": int(row["char_end"]),
                "word_start": start,
                "word_end": end,
                "token_start": token_start,
                "token_end": token_end,
                "embedding_model": LANCE_MODEL_NAME,
            }

            for representation in REPRESENTATIONS:
                vector = np.asarray(
                    row[f"vec_{representation}"],
                    dtype=np.float32,
                )

                if vector.shape != (VECTOR_DIM,):
                    raise ValueError(
                        f"{path.name}: {representation} vector "
                        f"has shape {vector.shape}, "
                        f"expected ({VECTOR_DIM},)"
                    )

                name = table_name(
                    representation,
                    int(year),
                )

                buffers[name].append({
                    **common,
                    "vector": vector.tolist(),
                })

                if len(buffers[name]) >= WRITE_BATCH_SIZE:
                    rows_written += writer.write(
                        name,
                        buffers[name],
                    )

                    buffers[name] = []

            if passages_seen >= next_log:
                logger.info(
                    "[passages] %s: processed %d passages",
                    path.name,
                    passages_seen,
                )
                next_log = (
                    (passages_seen // 10_000) + 1
                ) * 10_000

    rows_written += flush_buffers(
        writer,
        buffers,
    )

    logger.info(
        "[passages] %s: input passages=%d, "
        "new vector rows=%d",
        path.name,
        passages_seen,
        rows_written,
    )

    return passages_seen, rows_written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=( "Import multi-scale passage vectors into LanceDB." )
    )

    parser.add_argument(
        "--legacy-ids",
        action="store_true",
        default=False,
        help=(
            "Use the old passage_id formula when re-importing "
            "pre-multi-scale shards."
        ),
    )

    args = parser.parse_args()

    input_dir = INPUT_DIR.resolve()

    if not input_dir.exists():
        raise SystemExit( f"Passage input directory does not exist: {input_dir}" )

    shards = sorted( input_dir.glob("passages_*.parquet") )

    if not shards:
        raise SystemExit( f"No passages_*.parquet files found in {input_dir}" )

    logger.info( "[passages] input: %s", input_dir, )
    logger.info( "[passages] Lance root: %s", LANCE_INDEXES_DIR, )
    logger.info( "[passages] found %d shard(s)", len(shards), )
    logger.info( "[passages] legacy IDs: %s", args.legacy_ids, )

    writer = PassageWriter(
        LANCE_INDEXES_DIR
    )

    total_passages = 0
    total_vectors = 0

    for shard in shards:
        passages, vectors = import_shard(
            shard,
            writer,
            legacy_ids=args.legacy_ids,
        )

        total_passages += passages
        total_vectors += vectors

    if BUILD_INDEXES:
        writer.build_indexes()

    logger.info(
        "[passages] complete: passages read=%d, "
        "new vector rows=%d",
        total_passages,
        total_vectors,
    )

    for name, table in sorted(
        writer.tables.items()
    ):
        logger.info(
            "[passages] table %s: %d rows",
            name,
            table.count_rows(),
        )


if __name__ == "__main__":
    main()
