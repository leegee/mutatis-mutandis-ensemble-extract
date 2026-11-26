#!/usr/bin/env python3
"""Screen OSIS XML verses with the shared corpus whiteness filter.

Run from the backend/project environment where ``mutatis_mutandis`` imports.
The script does not connect to or write to PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import OUT_DIR;
from mutatis_mutandis.ingest.lib.osis import process_osis_file
from mutatis_mutandis.ingest.lib.inclusion_filter import (
    extract_sparse_windows,
    inclusion_filter_reason,
)


def _display_tokens(tokens: list[str]) -> str:
    """Readable rendering of the parser's normalized token stream."""
    # Preserve token content; punctuation is separated because the parser
    # deliberately returns tokens rather than a reconstructed source string.
    return " ".join(tokens)


def _window_records(sparse: list[tuple[int, str]]) -> list[dict[str, object]]:
    """Group sparse tokens into contiguous windows without hiding gaps."""
    if not sparse:
        return []

    groups: list[list[tuple[int, str]]] = []
    for item in sparse:
        if not groups or item[0] != groups[-1][-1][0] + 1:
            groups.append([item])
        else:
            groups[-1].append(item)

    return [
        {
            "start_token": group[0][0],
            "end_token": group[-1][0],
            "text": _display_tokens([token for _, token in group]),
        }
        for group in groups
    ]


def screen_files(inputs: list[Path], output: Path, include_rejected: bool = True) -> tuple[int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    passed_count = 0

    fieldnames = [
        "osis_ref",
        "doc_id",
        "title",
        "pub_year",
        "passes_filter",
        "filter_reason",
        "whiteness_score",
        "matched_terms",
        "matched_counts",
        "verse_tokens",
        "seed_windows",
        "source_file",
    ]

    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for source in inputs:
            records = process_osis_file(source)
            for meta, tokens in records:
                total += 1
                passed, reason, score, hits = inclusion_filter_reason(tokens)
                if passed:
                    passed_count += 1
                if not include_rejected and not passed:
                    continue
                if include_rejected and reason == "no_target_terms":
                    continue

                sparse = extract_sparse_windows(tokens)
                writer.writerow({
                    "osis_ref": meta.get("osis_ref", ""),
                    "doc_id": meta.get("doc_id", ""),
                    "title": meta.get("title", ""),
                    "pub_year": meta.get("pub_year", ""),
                    "passes_filter": passed,
                    "filter_reason": reason,
                    "whiteness_score": f"{score:.2f}",
                    "matched_terms": "; ".join(hits.keys()),
                    "matched_counts": json.dumps(dict(hits), ensure_ascii=False),
                    "verse_tokens": _display_tokens(tokens),
                    "seed_windows": json.dumps(_window_records(sparse), ensure_ascii=False),
                    "source_file": str(source),
                })

    return total, passed_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="+", type=Path, help="OSIS XML file(s) or directories")
    parser.add_argument("-o", "--output", type=Path, default=Path(OUT_DIR / "whiteness_screening.csv"))
    parser.add_argument(
        "--passed-only",
        "-p",
        "--pass",
        action="store_true",
        help="Write only verses that pass the filter (default: include rejected verses too)",
    )
    args = parser.parse_args()

    files: list[Path] = []
    for item in args.input:
        if item.is_dir():
            files.extend(sorted(item.rglob("*.xml")))
        elif item.is_file():
            files.append(item)
        else:
            parser.error(f"Input does not exist: {item}")

    if not files:
        parser.error("No input XML files found")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    total, passed = screen_files(files, args.output, include_rejected=not args.passed_only)
    print(f"Screened {total:,} verses; {passed:,} passed; {total - passed:,} rejected.")
    print(f"CSV written to: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
