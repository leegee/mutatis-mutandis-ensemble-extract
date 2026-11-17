#!/usr/bin/env python

"""
31_import_targets_to_lance.py - import per-occurrence target/context vectors
(21_colab_embed_targets.py output) into Lance.

The data is kept SEPARATE from the passage-window tables:

* its own Lance root (TARGETS_LANCE_DIR, a sibling of LANCE_INDEXES_DIR), so
  10_export_passage_windows.indexed_documents() never sees it;
* its own table, target_occurrence__<model>, one row per hit occurrence with
  six vector columns:

      vec_target_{l8,last,mean4}    the hit word itself
      vec_context_{l8,last,mean4}   everything else in the +/-50-word window

* its own identity: sha256 of (source, corpus, doc_id, hit_idx). The id names
  the occurrence, not its window, so re-embedding with a different window and
  --replace overwrites the same rows.

Only the target vectors get a vector index (neighbour search). Context vectors
are stored for analysis (e.g. target minus context) and are not indexed.

    # skip existing occurrences
    31_import_targets_to_lance.py

    # replace them
    31_import_targets_to_lance.py --replace
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, LANCE_MODEL_NAME
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_storage import fetch

logger = get_logger("targets2lance")

INPUT_SUBDIR = "output-targets"

# Sibling of the passage store. Move this into corpus_config once settled.
TARGETS_LANCE_DIR = Path(LANCE_INDEXES_DIR).parent / "lance_albinism_targets"
TABLE_NAME = f"target_occurrence__{LANCE_MODEL_NAME}"

ID_SOURCE = "target_occurrence_v1"

LAYERS = ("l8", "last", "mean4")
ROLES = ("target", "context")
VECTOR_COLUMNS = tuple(f"vec_{role}_{layer}" for role in ROLES for layer in LAYERS)
INDEXED_VECTOR_COLUMNS = tuple(f"vec_target_{layer}" for layer in LAYERS)
SCALAR_INDEX_COLUMNS = ("occurrence_id", "pub_year")

VECTOR_DIM = 768
# float32 matches the passage tables. The source parquet is float16, so
# switching both of these to float16 halves storage (about 18 KB/row -> 9 KB/row)
# if your Lance version supports float16 vector columns and IVF indexes.
VECTOR_TYPE = pa.float32()
VECTOR_NP_DTYPE = np.float32

READ_BATCH_SIZE = 2048

BUILD_INDEXES = True
VECTOR_INDEX_TYPE = "IVF_FLAT"
VECTOR_INDEX_METRIC = "cosine"
MIN_VECTOR_INDEX_PARTITIONS = 1
MAX_VECTOR_INDEX_PARTITIONS = 256

# Columns passed through unchanged from the parquet shard.
PASSTHROUGH = (
    "corpus", "doc_id", "pub_year", "hit_idx", "matched_token",
    "hit_groups", "routes", "token_start", "token_end",
    "n_context_words", "n_target_subwords",
)
REQUIRED = set(PASSTHROUGH) | set(VECTOR_COLUMNS)


# ---------------------------------------------------------------------------
# Identity and schema
# ---------------------------------------------------------------------------

def occurrence_id(corpus: str, doc_id: str, hit_idx: int) -> str:
    identity = f"{ID_SOURCE}\0{corpus}\0{doc_id}\0{int(hit_idx)}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def make_schema() -> pa.Schema:
    fields = [
        pa.field("occurrence_id", pa.string()),
        pa.field("corpus", pa.string()),
        pa.field("doc_id", pa.string()),
        pa.field("pub_year", pa.int32()),
        pa.field("hit_idx", pa.int32()),
        pa.field("matched_token", pa.string()),
        pa.field("hit_groups", pa.list_(pa.string())),
        pa.field("routes", pa.list_(pa.string())),
        pa.field("token_start", pa.int32()),
        pa.field("token_end", pa.int32()),
        pa.field("n_context_words", pa.int32()),
        pa.field("n_target_subwords", pa.int32()),
        pa.field("embedding_model", pa.string()),
    ]
    fields += [
        pa.field(name, pa.list_(VECTOR_TYPE, VECTOR_DIM))
        for name in VECTOR_COLUMNS
    ]
    return pa.schema(fields)


# ---------------------------------------------------------------------------
# Lance writer
# ---------------------------------------------------------------------------

class TargetWriter:
    """Idempotent writer for the single target-occurrence table."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(root))
        self.schema = make_schema()
        self.table = self._open_or_create()
        self._ids: set[str] | None = None

    def _open_or_create(self):
        if TABLE_NAME in set(self.db.list_tables().tables):
            table = self.db.open_table(TABLE_NAME)
            self._validate_schema(table)
            return table
        logger.info("creating Lance table %s", TABLE_NAME)
        return self.db.create_table(TABLE_NAME, schema=self.schema)

    def _validate_schema(self, table) -> None:
        actual = table.schema
        missing = set(self.schema.names) - set(actual.names)
        if missing:
            raise ValueError(
                f"table {TABLE_NAME} has an incompatible schema; "
                f"missing columns: {sorted(missing)}"
            )
        mismatched = [
            (f.name, str(actual.field(f.name).type), str(f.type))
            for f in self.schema
            if actual.field(f.name).type != f.type
        ]
        if mismatched:
            raise ValueError(
                f"table {TABLE_NAME} has incompatible field types: {mismatched}"
            )

    def known_ids(self) -> set[str]:
        if self._ids is None:
            n = self.table.count_rows()
            ids: set[str] = set()
            if n:
                col = (
                    self.table.search()
                    .select(["occurrence_id"])
                    .limit(n)
                    .to_arrow()
                    .column("occurrence_id")
                )
                ids = set(col.to_pylist())
            self._ids = ids
        return self._ids

    def write(self, batch: pa.Table, *, replace: bool = False) -> int:
        """
        Append new occurrences. Existing ids are skipped, or deleted and
        rewritten when replace=True. Duplicates inside the batch are dropped.
        """
        if batch.num_rows == 0:
            return 0

        known = self.known_ids()
        ids = batch.column("occurrence_id").to_pylist()

        keep: list[int] = []
        to_replace: set[str] = set()
        seen: set[str] = set()

        for i, oid in enumerate(ids):
            if oid in seen:
                continue
            seen.add(oid)
            if oid in known:
                if replace:
                    to_replace.add(oid)
                    keep.append(i)
            else:
                keep.append(i)

        if not keep:
            return 0

        if to_replace:
            ordered = sorted(to_replace)
            for i in range(0, len(ordered), 500):
                quoted = ",".join(f"'{oid}'" for oid in ordered[i:i + 500])
                self.table.delete(f"occurrence_id IN ({quoted})")
            known -= to_replace

        out = batch if len(keep) == len(ids) else batch.take(pa.array(keep))
        self.table.add(out, mode="append")
        known.update(ids[i] for i in keep)
        return len(keep)

    # -- indexes -----------------------------------------------------------

    def _index_complete(self, name: str) -> bool:
        indexes = {index.name: index for index in self.table.list_indices()}
        index = indexes.get(name)
        if index is None:
            return False
        unindexed = getattr(index, "num_unindexed_rows", None)
        if unindexed is None:
            try:
                unindexed = self.table.index_stats(name).num_unindexed_rows
            except Exception:
                return False        # cannot tell: rebuild
        return unindexed == 0

    def build_indexes(self) -> None:
        rows = self.table.count_rows()
        if rows == 0:
            return

        partitions = max(
            MIN_VECTOR_INDEX_PARTITIONS,
            min(MAX_VECTOR_INDEX_PARTITIONS, int(rows ** 0.5)),
        )

        for column in INDEXED_VECTOR_COLUMNS:
            name = f"{column}_idx"
            if self._index_complete(name):
                continue
            logger.info(
                "building vector index %s: %d rows, %d partitions",
                name, rows, partitions,
            )
            self.table.create_index(
                metric=VECTOR_INDEX_METRIC,
                index_type=VECTOR_INDEX_TYPE,
                vector_column_name=column,
                num_partitions=partitions,
                replace=True,
            )

        for column in SCALAR_INDEX_COLUMNS:
            name = f"{column}_idx"
            if self._index_complete(name):
                continue
            logger.info("building scalar index %s", name)
            self.table.create_scalar_index(
                column, index_type="BTREE", replace=True,
            )

    def compact(self) -> None:
        """Many small appends leave many fragments; merge them if supported."""
        try:
            self.table.optimize()
            logger.info("optimised %s", TABLE_NAME)
        except Exception as exc:
            logger.warning("table.optimize() unavailable or failed: %s", exc)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def vectors_as_matrix(column, name: str, path: Path) -> np.ndarray:
    arr = column.combine_chunks() if isinstance(column, pa.ChunkedArray) else column
    flat = arr.flatten().to_numpy(zero_copy_only=False)
    if flat.size % VECTOR_DIM:
        raise ValueError(
            f"{path.name}: {name} has {flat.size} values, "
            f"not a multiple of {VECTOR_DIM}"
        )
    matrix = flat.reshape(-1, VECTOR_DIM).astype(np.float32, copy=False)
    bad = ~np.isfinite(matrix).all(axis=1) | (np.abs(matrix).sum(axis=1) == 0)
    if bad.any():
        offsets = np.flatnonzero(bad)[:10].tolist()
        raise ValueError(
            f"{path.name}: {int(bad.sum())} invalid {name} vectors in batch; "
            f"batch row offsets={offsets}"
        )
    return matrix


def to_lance_table(batch: pa.RecordBatch, path: Path) -> pa.Table:
    src = pa.Table.from_batches([batch])
    n = src.num_rows
    schema = make_schema()

    corpus = src.column("corpus").to_pylist()
    doc_id = src.column("doc_id").to_pylist()
    hit_idx = src.column("hit_idx").to_pylist()
    years = src.column("pub_year").to_pylist()

    if any(year is None for year in years):
        raise ValueError(f"{path.name}: occurrence with no publication year")
    if any(h is None for h in hit_idx):
        raise ValueError(f"{path.name}: occurrence with no hit_idx")

    token_start = src.column("token_start").to_pylist()
    token_end = src.column("token_end").to_pylist()
    if any(e < s for s, e in zip(token_start, token_end)):
        raise ValueError(f"{path.name}: invalid token span (end < start)")

    arrays: dict[str, pa.Array | pa.ChunkedArray] = {
        "occurrence_id": pa.array(
            [occurrence_id(c, d, h) for c, d, h in zip(corpus, doc_id, hit_idx)],
            type=pa.string(),
        ),
    }
    for name in PASSTHROUGH:
        arrays[name] = src.column(name)
    arrays["embedding_model"] = pa.array([LANCE_MODEL_NAME] * n, type=pa.string())

    for name in VECTOR_COLUMNS:
        matrix = vectors_as_matrix(src.column(name), name, path)
        arrays[name] = pa.FixedSizeListArray.from_arrays(
            pa.array(matrix.astype(VECTOR_NP_DTYPE).ravel(), type=VECTOR_TYPE),
            VECTOR_DIM,
        )

    return pa.table(arrays).select(schema.names).cast(schema)


def import_shard(path: Path, writer: TargetWriter, *, replace: bool) -> tuple[int, int]:
    parquet = pq.ParquetFile(path)

    missing = REQUIRED - set(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"{path.name}: missing columns: {sorted(missing)}")

    seen = 0
    written = 0
    for batch in parquet.iter_batches(batch_size=READ_BATCH_SIZE):
        seen += batch.num_rows
        written += writer.write(to_lance_table(batch, path), replace=replace)

    logger.info("%s: input occurrences=%d, new rows=%d", path.name, seen, written)
    return seen, written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import per-occurrence target vectors into a separate Lance store."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=False,
        help="Overwrite existing occurrence_ids instead of skipping them.",
    )
    parser.add_argument(
        "--no-indexes",
        action="store_true",
        default=False,
        help="Skip index building (e.g. while importing in several passes).",
    )
    args = parser.parse_args()

    input_dir = fetch(INPUT_SUBDIR).resolve()
    if not input_dir.exists():
        raise SystemExit(f"Target input directory does not exist: {input_dir}")

    shards = sorted(input_dir.glob("targets_*.parquet"))
    if not shards:
        raise SystemExit(f"No targets_*.parquet files found in {input_dir}")

    logger.info("input: %s", input_dir)
    logger.info("Lance root: %s (separate from %s)", TARGETS_LANCE_DIR, LANCE_INDEXES_DIR)
    logger.info("table: %s", TABLE_NAME)
    logger.info("found %d shard(s)", len(shards))
    logger.info("replace existing: %s", args.replace)

    writer = TargetWriter(TARGETS_LANCE_DIR)

    total_seen = 0
    total_written = 0
    for shard in shards:
        seen, written = import_shard(shard, writer, replace=args.replace)
        total_seen += seen
        total_written += written

    writer.compact()
    if BUILD_INDEXES and not args.no_indexes:
        writer.build_indexes()

    logger.info(
        "complete: occurrences read=%d, new rows=%d, table rows=%d",
        total_seen, total_written, writer.table.count_rows(),
    )


if __name__ == "__main__":
    main()
