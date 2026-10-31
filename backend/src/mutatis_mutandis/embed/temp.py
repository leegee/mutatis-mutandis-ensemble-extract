
"""
migrate_lance_pub_years.py

Move LanceDB passage rows into the 50-year buckets implied by
corrected PostgreSQL document dates.

No embeddings are recomputed. All passage metadata and vectors are preserved.

The script:
  1. Reads corrected document dates from PostgreSQL.
  2. Finds matching rows still in the 1500_1549 source tables.
  3. Corrects pub_year before inserting into destination tables.
  4. Creates destination tables where necessary.
  5. Checks destination passage IDs before inserting.
  6. Verifies destination rows before deleting source rows.

Default: dry run.
Apply: --apply, followed by typing YES.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict

import lancedb
import pyarrow as pa

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR
from mutatis_mutandis.lib.corpus_db import get_connection


CORPUS = "misc"
OLD_YEAR = 1500
OLD_BUCKET = "1500_1549"

TABLE_RE = re.compile(
    r"^passage_(l8|last|mean4)__macberth__(\d{4})_(\d{4})$"
)


def year_bucket(year: int) -> str:
    """Return the 50-year bucket containing year."""
    start = (year // 50) * 50
    return f"{start}_{start + 49}"


def sql_quote(value: str) -> str:
    """Safely quote a string in a LanceDB filter expression."""
    return "'" + value.replace("'", "''") + "'"


def fetch_corrected_dates() -> dict[str, int]:
    """Read corrected document dates from PostgreSQL."""
    conn = get_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, pub_year
                FROM documents
                WHERE corpus = %s
                  AND pub_year IS NOT NULL
                  AND pub_year <> %s
                """,
                (CORPUS, OLD_YEAR),
            )

            return {
                doc_id: int(pub_year)
                for doc_id, pub_year in cur.fetchall()
            }
    finally:
        conn.close()


def fetch_arrow(table, predicate: str) -> pa.Table:
    """Retrieve complete rows matching a LanceDB filter."""
    return table.search().where(predicate).to_arrow()


def passage_ids(arrow_table: pa.Table) -> set[str]:
    """Extract passage IDs from an Arrow table."""
    return {
        row["passage_id"]
        for row in arrow_table.select(
            ["passage_id"]
        ).to_pylist()
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move incorrectly dated LanceDB passage rows."
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration. Default is dry-run.",
    )

    args = parser.parse_args()

    db = lancedb.connect(LANCE_INDEXES_DIR)

    table_names = set(db.list_tables().tables)

    source_tables = sorted(
        name
        for name in table_names
        if (
            (match := TABLE_RE.match(name))
            and match.group(2) + "_" + match.group(3) == OLD_BUCKET
        )
    )

    if not source_tables:
        print(f"No source tables found for {OLD_BUCKET}.")
        return

    corrected_dates = fetch_corrected_dates()

    if not corrected_dates:
        print("No corrected PostgreSQL dates found.")
        return

    print(f"Corrected PostgreSQL documents: {len(corrected_dates)}")
    print(f"Source tables: {len(source_tables)}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    # ---------------------------------------------------------
    # Build the complete migration plan before changing anything.
    # ---------------------------------------------------------

    plans = []

    for source_name in source_tables:
        match = TABLE_RE.match(source_name)
        representation = match.group(1)

        source = db.open_table(source_name)

        doc_ids = sorted(corrected_dates)

        # Build a safe IN clause.
        doc_filter = ", ".join(
            sql_quote(doc_id)
            for doc_id in doc_ids
        )

        predicate = (
            f"corpus = {sql_quote(CORPUS)} "
            f"AND pub_year = {OLD_YEAR} "
            f"AND doc_id IN ({doc_filter})"
        )

        source_rows = fetch_arrow(source, predicate)

        if source_rows.num_rows == 0:
            print(f"{source_name}: no matching rows")
            continue

        grouped = defaultdict(list)

        for row in source_rows.to_pylist():
            doc_id = row["doc_id"]

            if doc_id not in corrected_dates:
                continue

            new_year = corrected_dates[doc_id]

            # IMPORTANT:
            # Correct the row metadata before creating the
            # destination Arrow table.
            row["pub_year"] = new_year

            destination_bucket = year_bucket(new_year)

            grouped[
                (doc_id, new_year, destination_bucket)
            ].append(row)

        for (
            doc_id,
            new_year,
            destination_bucket,
        ), rows in grouped.items():

            destination_name = (
                f"passage_{representation}__macberth__"
                f"{destination_bucket}"
            )

            plans.append({
                "source_name": source_name,
                "destination_name": destination_name,
                "doc_id": doc_id,
                "new_year": new_year,
                "rows": rows,
                "representation": representation,
            })

    if not plans:
        print("\nNo matching Lance rows need moving.")
        return

    # ---------------------------------------------------------
    # Summarise the planned moves.
    # ---------------------------------------------------------

    summary = defaultdict(
        lambda: {"documents": 0, "rows": 0}
    )

    for plan in plans:
        destination = plan["destination_name"]

        summary[destination]["documents"] += 1
        summary[destination]["rows"] += len(plan["rows"])

    print("\nPlanned moves:")

    for destination, counts in sorted(summary.items()):
        print(
            f"  {destination}: "
            f"{counts['documents']} documents, "
            f"{counts['rows']} passage rows"
        )

    total_rows = sum(
        len(plan["rows"])
        for plan in plans
    )

    print(f"\nTotal document/table moves: {len(plans)}")
    print(f"Total passage rows: {total_rows}")

    if not args.apply:
        print("\nDRY RUN ONLY. No LanceDB data has been changed.")
        print("Run with --apply to perform the migration.")
        return

    # ---------------------------------------------------------
    # Require explicit confirmation.
    # ---------------------------------------------------------

    print(
        "\nThis will insert rows into destination tables and "
        "delete the verified source rows."
    )

    confirmation = input("Type YES to continue: ")

    if confirmation != "YES":
        print("Cancelled.")
        return

    # ---------------------------------------------------------
    # Apply the migration, one document/representation at a time.
    # ---------------------------------------------------------

    moved_rows = 0

    for index, plan in enumerate(plans, start=1):

        source_name = plan["source_name"]
        destination_name = plan["destination_name"]
        doc_id = plan["doc_id"]
        new_year = plan["new_year"]
        rows = plan["rows"]

        source = db.open_table(source_name)

        source_predicate = (
            f"corpus = {sql_quote(CORPUS)} "
            f"AND doc_id = {sql_quote(doc_id)} "
            f"AND pub_year = {OLD_YEAR}"
        )

        destination_predicate = (
            f"corpus = {sql_quote(CORPUS)} "
            f"AND doc_id = {sql_quote(doc_id)} "
            f"AND pub_year = {new_year}"
        )

        # Reconstruct the expected complete rows using the
        # source schema. Vectors and all metadata are retained.
        expected = pa.Table.from_pylist(
            rows,
            schema=source.schema,
        )

        expected_ids = passage_ids(expected)

        if len(expected_ids) != len(rows):
            raise RuntimeError(
                f"Duplicate passage IDs in source for {doc_id}. "
                "Source rows have been retained."
            )

        # Refresh table names in case an earlier plan created
        # a destination table.
        current_names = set(db.list_tables().tables)

        # -----------------------------------------------------
        # Create or open destination.
        # -----------------------------------------------------

        if destination_name in current_names:

            destination = db.open_table(destination_name)

            existing = fetch_arrow(
                destination,
                destination_predicate,
            )

            existing_ids = passage_ids(existing)

            if existing.num_rows != len(existing_ids):
                raise RuntimeError(
                    f"Duplicate passage IDs already exist in "
                    f"{destination_name} for {doc_id}. "
                    "Source rows have been retained."
                )

            unexpected_ids = existing_ids - expected_ids

            if unexpected_ids:
                raise RuntimeError(
                    f"Unexpected destination passage IDs for "
                    f"{doc_id} in {destination_name}. "
                    "Source rows have been retained."
                )

            missing_ids = expected_ids - existing_ids

            if missing_ids:

                missing_rows = [
                    row
                    for row in rows
                    if row["passage_id"] in missing_ids
                ]

                to_add = pa.Table.from_pylist(
                    missing_rows,
                    schema=source.schema,
                )

                destination.add(to_add)

        else:

            destination = db.create_table(
                destination_name,
                data=expected,
            )

        # -----------------------------------------------------
        # Verify destination before deleting source.
        # -----------------------------------------------------

        verified = fetch_arrow(
            destination,
            destination_predicate,
        )

        verified_ids = passage_ids(verified)

        if (
            verified.num_rows != len(expected_ids)
            or verified_ids != expected_ids
        ):
            raise RuntimeError(
                f"Destination verification failed for {doc_id} "
                f"in {destination_name}. "
                "Source rows have been retained."
            )

        # -----------------------------------------------------
        # Delete source rows only after destination verification.
        # -----------------------------------------------------

        source.delete(source_predicate)

        remaining = source.count_rows(
            filter=source_predicate
        )

        if remaining != 0:
            raise RuntimeError(
                f"Source deletion verification failed for "
                f"{doc_id}: {remaining} rows remain."
            )

        moved_rows += len(rows)

        print(
            f"[{index}/{len(plans)}] "
            f"{doc_id}: {len(rows)} rows -> {destination_name}"
        )

    print("\nMigration completed.")
    print(f"Passage rows moved: {moved_rows}")


if __name__ == "__main__":
    main()
