
from pathlib import Path
import re
import sys

import pyarrow.parquet as pq

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_logging import logger

# D:\src\mutatis-mutandis\out\tier1
CHECKPOINT_DIR = OUT_DIR / "export" / "_checkpoints"
OUTPUT_PATH = OUT_DIR / "tier1" / "passages" / "passages_00000.parquet"

REQUIRED_COLUMNS = {
    "corpus", "doc_id", "pub_year",
    "word_start", "word_end",
    "token_start", "token_end",
    "vec_l8", "vec_last", "vec_mean4",
}


def checkpoint_index(path):
    match = re.fullmatch(r"doc_(\d+)\.parquet", path.name)
    return int(match.group(1)) if match else None


def main():
    files = sorted(
        (
            p for p in CHECKPOINT_DIR.rglob("doc_*.parquet")
            if checkpoint_index(p) is not None
        ),
        key=lambda p: (p.parent.as_posix(), checkpoint_index(p)),
    )

    if not files:
        raise RuntimeError(f"No checkpoints found in {CHECKPOINT_DIR}")

    # Validate every checkpoint before writing the output.
    schema = None
    total_rows = 0

    for path in files:
        pf = pq.ParquetFile(path)
        current_schema = pf.schema_arrow

        missing = REQUIRED_COLUMNS - set(current_schema.names)
        if missing:
            raise RuntimeError(
                f"{path.name}: missing columns {sorted(missing)}"
            )

        if schema is None:
            schema = current_schema
        elif not current_schema.equals(schema, check_metadata=False):
            raise RuntimeError(f"Schema mismatch: {path.name}")

        if pf.metadata.num_rows <= 0:
            raise RuntimeError(f"Empty checkpoint: {path.name}")

        total_rows += pf.metadata.num_rows

    logger.info(f"Checkpoints: {len(files)}")
    logger.info(f"Expected passage rows: {total_rows:,}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = OUTPUT_PATH.with_suffix(".parquet.part")
    temp_path.unlink(missing_ok=True)

    writer = None
    written_rows = 0

    try:
        for i, path in enumerate(files, 1):
            table = pq.read_table(path)

            if writer is None:
                writer = pq.ParquetWriter(
                    temp_path, table.schema, compression="zstd"
                )

            writer.write_table(table)
            written_rows += table.num_rows
            del table

            if i % 25 == 0 or i == len(files):
                logger.info(
                    f"Written {i}/{len(files)} checkpoints; "
                    f"{written_rows:,} passage rows; "
                    f"current source: {path.parent.name}"
                )
    finally:
        if writer is not None:
            writer.close()

    # Verify the output before publishing it.
    with pq.ParquetFile(temp_path) as result:
        actual_rows = result.metadata.num_rows

    if actual_rows != total_rows:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Row-count mismatch: expected {total_rows}, got {actual_rows}"
        )

    # Replace the destination only after successful validation.
    temp_path.replace(OUTPUT_PATH)

    logger.info(f"ASSEMBLED: {OUTPUT_PATH}")
    logger.info(f"Passage rows: {actual_rows:,}")
    logger.info(f"Output size: {OUTPUT_PATH.stat().st_size / (1024**3):.2f} GiB")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.info(f"ERROR: {exc}", file=sys.stderr)
        raise
