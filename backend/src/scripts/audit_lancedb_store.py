#!/usr/bin/env python3
"""Read-only inventory of the project's local LanceDB store."""

from __future__ import annotations

import argparse
from pathlib import Path

import lancedb


DEFAULT_LANCE_DIR = (
    Path(__file__).resolve().parents[3]
    / "out"
    / "indexes"
    / "lance_albinism_ensemble"
)


def all_table_names(db) -> list[str]:
    """Collect every table name, following LanceDB's page tokens."""
    names: list[str] = []
    page_token = None

    while True:
        page = db.list_tables(page_token=page_token, limit=1000)
        names.extend(page.tables)
        page_token = page.page_token
        if not page_token:
            break

    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lance-dir",
        type=Path,
        default=DEFAULT_LANCE_DIR,
        help=f"LanceDB directory (default: {DEFAULT_LANCE_DIR})",
    )
    parser.add_argument(
        "--corpus",
        help="count rows and list text IDs for this corpus, for example: cme",
    )
    args = parser.parse_args()

    if not args.lance_dir.is_dir():
        raise SystemExit(f"LanceDB directory not found: {args.lance_dir}")

    db = lancedb.connect(str(args.lance_dir))
    names = all_table_names(db)
    print(f"LanceDB: {args.lance_dir}")
    print(f"Tables: {len(names)}")
    print(f"LanceDB version: {lancedb.__version__}")
    print()

    corpus_doc_ids: set[str] = set()
    for name in names:
        table = db.open_table(name)
        row_count = table.count_rows()
        columns = ", ".join(
            f"{field.name}:{field.type}" for field in table.schema
        )
        line = f"{name}\trows={row_count}\tcolumns={columns}"

        if args.corpus:
            if "corpus" in table.schema.names:
                value = args.corpus.replace("'", "''")
                corpus_filter = f"corpus = '{value}'"
                matching_rows = table.count_rows(filter=corpus_filter)
                line += f"\t{args.corpus}_rows={matching_rows}"

                if matching_rows and "doc_id" in table.schema.names:
                    result = (
                        table.search()
                        .where(corpus_filter)
                        .select(["doc_id"])
                        .limit(matching_rows)
                        .to_arrow()
                    )
                    corpus_doc_ids.update(
                        doc_id
                        for doc_id in result.column("doc_id").to_pylist()
                        if doc_id
                    )
            else:
                line += "\tcorpus_rows=(no corpus column)"

        print(line)

    if args.corpus:
        print(f"\nTexts found for corpus {args.corpus}: {len(corpus_doc_ids)}")
        if corpus_doc_ids:
            for doc_id in sorted(corpus_doc_ids):
                print(f"  {doc_id}")
        else:
            print("  (none)")


if __name__ == "__main__":
    main()
