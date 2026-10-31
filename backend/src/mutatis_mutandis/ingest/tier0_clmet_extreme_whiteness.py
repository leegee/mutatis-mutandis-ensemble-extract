#!/usr/bin/env python
"""
tier0_clmet_extreme_whiteness.py

Create derived CLMET documents for every source document represented in
the bodily-whiteness concordance and insert the COMPLETE source document
text into PostgreSQL.

This is deliberately independent of the existing EEBO/ECCO ingestion
pipeline.

The concordance is used only to determine WHICH CLMET source documents
belong in the derived corpus. Once a source document is selected, the
entire textual body is ingested:

    concordance
        |
        +-- document A --+
        +-- document B --+
        +-- document C --+
                         |
                         v
                  complete source text
                         |
                         v
                      documents
                         |
                         v
                       tokens

No context extraction is performed.

The resulting document receives:

    doc_id = "CLMET3" + original document id

and retains the original source filepath and CLMET metadata.

The extracted documents are inserted using the existing documents/tokens
schema. No database schema changes are required.

Existing derived documents are skipped. This prevents rerunning the
extraction from creating duplicate token rows. Use `--clear` to remove
existing derived documents and their tokens.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from psycopg import sql

import lib.corpus_config as config
import lib.corpus_db as corpus_db
from lib.corpus_logging import logger


CORPUS_NAME = "clmet"

CLMET_TEXT_DIR = config.CLMET_CORPUS_INPUT_DIR / "txt"

CONCORDANCE_FILE = (
    config.CLMET_CORPUS_INPUT_DIR
    / ".."
    / ".."
    / "extreme_whiteness"
    / "bodily_whiteness_concordance.csv"
)

TOKEN_RE = re.compile(r"\w+|[^\w\s]")


DOC_ID_FIELDS = (
    "doc_id",
    "document_id",
    "document",
    "doc",
    "filename",
    "file",
    "filepath",
    "path",
)

HIT_FIELDS = (
    "whiteness_surface",
    "whiteness_lemma",
    "hit",
    "keyword",
    "target",
    "term",
    "match",
    "matched",
)


def resolve_column(
    fieldnames: list[str],
    candidates: tuple[str, ...],
) -> str | None:
    """Resolve a CSV column name case-insensitively."""

    lowered = {
        field.strip().lower(): field
        for field in fieldnames
        if field
    }

    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]

    return None


def normalise_doc_id(value: str) -> str:
    """
    Turn a CSV document reference into the source document identifier.

    For example:

        CLMET3_1_1_42.txt

    becomes:

        CLMET3_1_1_42
    """

    value = value.strip()
    value = value.replace("\\", "/")

    value = Path(value).name

    if value.lower().endswith(".txt"):
        value = value[:-4]

    return value


def find_source_file(doc_ref: str) -> Path | None:
    """
    Locate the CLMET source text.

    Try the supplied value as a relative path first, then as a filename
    beneath txt/, and finally search recursively beneath txt/.
    """

    ref = doc_ref.replace("\\", "/")

    candidates: list[Path] = []

    p = Path(ref)

    if not p.is_absolute():
        candidates.append(
            config.CLMET_CORPUS_INPUT_DIR / p
        )
        candidates.append(
            CLMET_TEXT_DIR / p
        )

    name = Path(ref).name

    if not name.lower().endswith(".txt"):
        name += ".txt"

    candidates.append(
        CLMET_TEXT_DIR / name
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    matches = list(
        CLMET_TEXT_DIR.rglob(name)
    )

    if matches:
        return matches[0]

    return None


def inspect_source_markup(
    text: str,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Inventory XML-like tags and character entities inside <text>.

    This is read-only diagnostics. It establishes the actual CLMET
    markup vocabulary before structural tags are removed.
    """

    match = re.search(
        r"<text\b[^>]*>(.*?)</text\s*>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if match is None:
        raise ValueError(
            "CLMET source has no <text>...</text> boundary"
        )

    body = match.group(1)

    tags: dict[str, int] = defaultdict(int)
    entities: dict[str, int] = defaultdict(int)

    for tag in re.findall(
        r"</?([A-Za-z][\w:-]*)\b[^>]*>",
        body,
    ):
        tags[tag.lower()] += 1

    for entity in re.findall(
        r"&([A-Za-z][A-Za-z0-9]+);",
        body,
    ):
        entities[entity.lower()] += 1

    return dict(tags), dict(entities)


def extract_source_text(text: str) -> str:
    """
    Extract the corpus text from a CLMET source file.

    The <text> element defines the corpus boundary. XML-like markup
    inside that boundary is structural and must not become corpus tokens.

    A missing boundary is a malformed source and therefore an error;
    ingesting the metadata/header as corpus text would corrupt the
    document while appearing superficially successful.
    """

    match = re.search(
        r"<text\b[^>]*>(.*?)</text\s*>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if match is None:
        raise ValueError(
            "CLMET source has no <text>...</text> boundary"
        )

    body = match.group(1)

    body = re.sub(
        r"<[^>]+>",
        " ",
        body,
    )

    body = re.sub(
        r"[ \t]+",
        " ",
        body,
    )

    body = re.sub(
        r"\n[ \t]+",
        "\n",
        body,
    )

    return body.strip()


def tokenize_source_text(
    text: str,
) -> list[str]:
    """
    Tokenise the complete CLMET source text using the existing corpus
    tokenisation convention.
    """

    return TOKEN_RE.findall(text)


def clear_derived_documents() -> None:
    """
    Delete previously generated CLMET extreme-whiteness documents
    and their tokens.

    These derived documents use the CLMET3-prefixed doc_id namespace.
    The tokens table has no FK to documents, so token rows must be
    deleted explicitly.
    """

    with corpus_db.get_connection(
        application_name="tier0-clmet-extreme-whiteness-clear",
    ) as conn:

        with conn.transaction():

            with conn.cursor() as cur:

                cur.execute("""
                    DELETE FROM tokens
                    WHERE corpus = 'clmet'
                      AND doc_id LIKE 'CLMET3%';
                """)

                token_count = cur.rowcount

                cur.execute("""
                    DELETE FROM documents
                    WHERE corpus = 'clmet'
                      AND doc_id LIKE 'CLMET3%';
                """)

                document_count = cur.rowcount

                logger.info(
                    f"[clmet] Cleared {document_count:,} derived documents "
                    f"and {token_count:,} tokens"
                )


def midpoint(a: int, b: int) -> int:
    """Return integer midpoint, rounded to nearest year."""

    return int(round((a + b) / 2))


def expand_short_year(
    start: int,
    end_raw: str,
) -> int:
    """
    Expand abbreviated CLMET year ranges.

    Examples:

        1730-1  -> 1731
        1740-41 -> 1741
        1760-1  -> 1761
        1773-4  -> 1774
        1780-96 -> 1796
        1820-2  -> 1822
        1810-3  -> 1813
        1904-5  -> 1905
        1888-9  -> 1889
    """

    end = int(end_raw)

    if len(end_raw) == 1:
        end = (start // 10) * 10 + end

    elif len(end_raw) == 2:
        end = (start // 100) * 100 + end

    else:
        end = int(end_raw)

    if end < start:
        end += 100

    return end


def clean_metadata_value(
    value: str,
) -> str:
    """
    Remove CLMET annotation prefixes while retaining the actual date.

    Examples:

        ?1750      -> 1750
        X1780-96   -> 1780-96
        a1911      -> 1911
    """

    value = value.strip()

    value = (
        value
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )

    value = re.sub(
        r"^[?XaA]+",
        "",
        value,
    )

    return value.strip()


def parse_year(
    value: str | None,
) -> int | None:
    """
    Parse a CLMET <year> value.

    Examples:

        1750       -> 1750
        ?1750      -> 1750
        1730-1     -> 1730
        1780-96    -> 1788
        1746-71    -> 1759
        1796-1817  -> 1807
    """

    if not value:
        return None

    value = clean_metadata_value(value)

    m = re.fullmatch(
        r"(\d{4})",
        value,
    )

    if m:
        return int(m.group(1))

    m = re.fullmatch(
        r"(\d{4})\s*-\s*(\d{1,4})",
        value,
    )

    if m:
        start = int(m.group(1))
        end_raw = m.group(2)

        end = expand_short_year(
            start,
            end_raw,
        )

        return midpoint(
            start,
            end,
        )

    return None


def parse_decade(
    value: str | None,
) -> int | None:
    """
    Parse a CLMET <decade> value.

    Examples:

        1750s -> 1755
        1710s -> 1715
    """

    if not value:
        return None

    value = clean_metadata_value(value)

    m = re.fullmatch(
        r"(\d{4})s",
        value,
    )

    if m:
        return int(m.group(1)) + 5

    return None


def parse_period(
    value: str | None,
) -> int | None:
    """
    Parse a CLMET <period> as a last-resort range.

    Examples:

        1710-1780 -> 1745
        1780-1850 -> 1815
        1850-1920 -> 1885
    """

    if not value:
        return None

    value = clean_metadata_value(value)

    m = re.fullmatch(
        r"(\d{4})\s*-\s*(\d{4})",
        value,
    )

    if m:
        return midpoint(
            int(m.group(1)),
            int(m.group(2)),
        )

    return None


def derive_pub_year(
    year_raw: str | None,
    decade_raw: str | None,
    period_raw: str | None,
) -> tuple[int | None, str | None]:
    """
    Derive a single publication year from CLMET metadata.

    Priority:

        <year>
        <decade>
        <period>

    Ranges are represented by their midpoint.

    Returns:

        (derived_year, source)
    """

    if year_raw:
        derived = parse_year(year_raw)

        if derived is not None:
            return derived, "year"

    if decade_raw:
        derived = parse_decade(decade_raw)

        if derived is not None:
            return derived, "decade"

    if period_raw:
        derived = parse_period(period_raw)

        if derived is not None:
            return derived, "period"

    return None, None


def metadata_from_text_file(
    doc_id: str,
    filepath: Path,
    token_count: int,
) -> dict:
    """
    Extract CLMET metadata from the XML-like header in the source file.

    Publication year is derived using:

        <year>
        <decade>
        <period>

    Ranges are converted to their midpoint.

    The source filepath remains relative to
    config.CLMET_CORPUS_INPUT_DIR.
    """

    text = filepath.read_text(
        encoding="utf-8",
        errors="replace",
    )

    header = text.split(
        "<text>",
        1,
    )[0]

    def get_tag(
        tag: str,
    ) -> str | None:

        match = re.search(
            rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>",
            header,
            flags=re.DOTALL,
        )

        if not match:
            return None

        value = match.group(1).strip()

        return value or None

    title = get_tag("title")
    author = get_tag("author")

    year_raw = get_tag("year")
    decade_raw = get_tag("decade")
    period_raw = get_tag("period")

    pub_year, year_source = derive_pub_year(
        year_raw,
        decade_raw,
        period_raw,
    )

    if pub_year is None:

        logger.warning(
            f"[clmet] Could not derive publication year for "
            f"{doc_id}: "
            f"year={year_raw!r}, "
            f"decade={decade_raw!r}, "
            f"period={period_raw!r}"
        )

    else:

        logger.debug(
            f"[clmet] {doc_id}: "
            f"pub_year={pub_year} "
            f"(source={year_source})"
        )

    return {
        "corpus": CORPUS_NAME,
        "doc_id": f"CLMET3{doc_id}",

        "filepath": filepath.relative_to(
            config.CORPUS_ROOT_DIR
        ).as_posix(),

        "title": title,
        "author": author,
        "pub_year": pub_year,

        "publisher": None,
        "pub_place": None,

        "source_date_raw": period_raw,

        "token_count": token_count,
        "lang": "eng",
    }


def existing_document_ids(
    conn,
    doc_ids: list[str],
) -> set[str]:
    """
    Return derived document IDs already present in documents.
    """

    if not doc_ids:
        return set()

    cur = conn.execute(
        """
        SELECT doc_id
        FROM documents
        WHERE corpus = %s
          AND doc_id = ANY(%s)
        """,
        (
            CORPUS_NAME,
            doc_ids,
        ),
    )

    return {
        row[0]
        for row in cur.fetchall()
    }


def insert_document_with_tokens(
    conn,
    metadata: dict,
    tokens: list[str],
) -> None:
    """
    Insert one derived document and all of its tokens in a single
    PostgreSQL transaction.

    The document row and all token rows are committed atomically:
    either the complete document is inserted, or nothing is.

    Existing rows for the same corpus/doc_id are removed first so that
    rerunning the ingestor is safe after an interrupted or partial run.
    """

    document_stmt = """
        INSERT INTO documents (
            corpus,
            doc_id,
            title,
            author,
            pub_year,
            publisher,
            pub_place,
            source_date_raw,
            token_count,
            filepath,
            lang
        )
        VALUES (
            %(corpus)s,
            %(doc_id)s,
            %(title)s,
            %(author)s,
            %(pub_year)s,
            %(publisher)s,
            %(pub_place)s,
            %(source_date_raw)s,
            %(token_count)s,
            %(filepath)s,
            %(lang)s
        )
    """

    token_stmt = sql.SQL(
        """
        COPY tokens (
            corpus,
            doc_id,
            token_idx,
            token
        )
        FROM STDIN
        WITH (
            FORMAT text,
            DELIMITER E'\\t',
            NULL '\\N'
        )
        """
    )

    def copy_escape(value: str) -> str:
        """
        Escape a value for PostgreSQL COPY ... FORMAT text.

        In COPY text format:

            \\  -> \\\\
            tab -> \\t
            LF  -> \\n
            CR  -> \\r
        """

        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("\t", "\\t")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )

    corpus = metadata["corpus"]
    doc_id = metadata["doc_id"]

    with conn.transaction():

        with conn.cursor() as cur:

            cur.execute(
                """
                DELETE FROM tokens
                WHERE corpus = %s
                  AND doc_id = %s
                """,
                (corpus, doc_id),
            )

            cur.execute(
                """
                DELETE FROM documents
                WHERE corpus = %s
                  AND doc_id = %s
                """,
                (corpus, doc_id),
            )

            cur.execute(
                document_stmt,
                metadata,
            )

            with cur.copy(token_stmt) as copy:
                for token_idx, token in enumerate(tokens):
                    row = (
                        f"{copy_escape(corpus)}\t"
                        f"{copy_escape(doc_id)}\t"
                        f"{token_idx}\t"
                        f"{copy_escape(token.lower())}\n"
                    )

                    copy.write(row)


def load_concordance(
    path: Path,
) -> dict[str, list[dict[str, str]]]:
    """
    Load the concordance and group rows by source document.

    The concordance is used to identify which complete CLMET source
    documents should be ingested.

    Individual concordance hits are retained for reporting, but they are
    NOT used to extract contexts.
    """

    if not path.is_file():
        raise FileNotFoundError(
            f"Concordance file not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise RuntimeError(
                f"No CSV header found in {path}"
            )

        doc_column = resolve_column(
            reader.fieldnames,
            DOC_ID_FIELDS,
        )

        file_column = resolve_column(
            reader.fieldnames,
            (
                "file",
                "filepath",
                "path",
                "filename",
            ),
        )

        hit_column = resolve_column(
            reader.fieldnames,
            HIT_FIELDS,
        )

        if doc_column is None:
            raise RuntimeError(
                "Could not identify the document column in "
                f"{path}.\n\nAvailable columns:\n"
                + "\n".join(
                    f"  {x}"
                    for x in reader.fieldnames
                )
            )

        if file_column is None:
            raise RuntimeError(
                "Could not identify the source file column in "
                f"{path}.\n\nAvailable columns:\n"
                + "\n".join(
                    f"  {x}"
                    for x in reader.fieldnames
                )
            )

        if hit_column is None:
            raise RuntimeError(
                "Could not identify the hit column in "
                f"{path}.\n\nAvailable columns:\n"
                + "\n".join(
                    f"  {x}"
                    for x in reader.fieldnames
                )
            )

        logger.info(
            f"[clmet] concordance document column: {doc_column}"
        )
        logger.info(
            f"[clmet] concordance file column: {file_column}"
        )
        logger.info(
            f"[clmet] concordance hit column: {hit_column}"
        )

        grouped: dict[
            str,
            list[dict[str, str]],
        ] = defaultdict(list)

        for row in reader:
            doc_value = (
                row.get(doc_column) or ""
            ).strip()

            source_file = (
                row.get(file_column) or ""
            ).strip()

            hit_value = (
                row.get(hit_column) or ""
            ).strip()

            if not doc_value:
                continue

            doc_id = normalise_doc_id(doc_value)

            if not doc_id:
                continue

            if not source_file:
                logger.warning(
                    f"[clmet] No source file recorded for document "
                    f"{doc_id}"
                )
                continue

            if not hit_value:
                continue

            occurrence = {
                key: (value or "").strip()
                for key, value in row.items()
                if key
            }

            occurrence["source_file"] = source_file
            occurrence["whiteness_surface"] = hit_value

            grouped[doc_id].append(occurrence)

    return dict(grouped)


def process(
    concordance_path: Path,
    limit: int | None = None,
    dry_run: bool = False,
) -> None:

    grouped = load_concordance(concordance_path)

    logger.info(
        f"[clmet] Documents represented in concordance: "
        f"{len(grouped):,}"
    )

    derived_doc_ids = [
        f"CLMET3{doc_id}"
        for doc_id in grouped
    ]

    processed = 0
    skipped_existing = 0
    missing = 0
    no_text = 0

    total_source_tokens = 0
    total_concordance_occurrences = 0
    total_tokens_inserted = 0

    with corpus_db.get_connection(
        application_name="tier0-clmet-extreme-whiteness",
    ) as conn:

        existing_ids = existing_document_ids(
            conn,
            derived_doc_ids,
        )

        if existing_ids:
            logger.info(
                "[clmet] Existing derived documents: "
                f"{len(existing_ids):,} "
                "(will be skipped)"
            )

        for doc_id, occurrences in grouped.items():

            if limit is not None and processed >= limit:
                break

            derived_doc_id = f"CLMET3{doc_id}"

            if derived_doc_id in existing_ids:
                logger.info(
                    f"[clmet] Skipping existing document {derived_doc_id}"
                )
                skipped_existing += 1
                continue

            source_files = {
                occurrence["source_file"]
                for occurrence in occurrences
                if occurrence.get("source_file")
            }

            if len(source_files) > 1:
                raise RuntimeError(
                    f"Multiple source files recorded for {doc_id}: "
                    f"{sorted(source_files)}"
                )

            source_file = next(
                iter(source_files),
                "",
            )

            if not source_file:
                logger.warning(
                    f"[clmet] Source text not found for {doc_id}"
                )
                missing += 1
                continue

            source_path = find_source_file(source_file)

            if source_path is None:
                logger.warning(
                    f"[clmet] Source text not found for {doc_id}: "
                    f"{source_file}"
                )
                missing += 1
                continue

            try:
                raw_text = source_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception as exc:
                logger.warning(
                    f"[clmet] Failed reading {source_path}: {exc}"
                )
                missing += 1
                continue

            source_text = extract_source_text(raw_text)

            if not source_text:
                logger.warning(
                    f"[clmet] Empty source text for {doc_id}"
                )
                no_text += 1
                continue

            tokens = tokenize_source_text(source_text)

            if not tokens:
                logger.warning(
                    f"[clmet] No tokens generated for {doc_id}"
                )
                no_text += 1
                continue

            metadata = metadata_from_text_file(
                doc_id,
                source_path,
                len(tokens),
            )

            concordance_count = len(occurrences)

            if dry_run:

                logger.info(
                    f"[clmet] {doc_id}: "
                    f"{concordance_count} concordance occurrences, "
                    f"COMPLETE SOURCE, "
                    f"{len(tokens):,} tokens"
                )

                logger.debug(
                    "[clmet] DRY RUN document:\n"
                    f"  doc_id: {metadata['doc_id']}\n"
                    f"  filepath: {metadata['filepath']}\n"
                    f"  title: {metadata['title']!r}\n"
                    f"  author: {metadata['author']!r}\n"
                    f"  pub_year: {metadata['pub_year']}\n"
                    f"  token_count: {metadata['token_count']}\n"
                    f"  first tokens: {tokens[:50]}\n"
                )

            else:

                try:
                    insert_document_with_tokens(
                        conn,
                        metadata,
                        tokens,
                    )

                except Exception:

                    logger.error(
                        f"[clmet] FAILED inserting "
                        f"{derived_doc_id}"
                    )

                    raise

                logger.info(
                    f"[clmet] {doc_id}: "
                    f"{concordance_count} concordance occurrences, "
                    f"COMPLETE SOURCE, "
                    f"{len(tokens):,} tokens inserted"
                )

            processed += 1

            total_source_tokens += len(tokens)
            total_concordance_occurrences += concordance_count
            total_tokens_inserted += len(tokens)

        logger.info(
            f"[clmet] Prepared {processed:,} complete documents"
        )

        if dry_run:

            logger.info(
                f"[clmet] DRY RUN: {processed:,} documents "
                "would be inserted"
            )

        else:

            logger.info(
                f"[clmet] Inserted {processed:,} complete documents "
                f"and {total_tokens_inserted:,} tokens"
            )

            corpus_db.refresh_views(conn)

    print()
    print("=" * 72)

    if dry_run:
        print("CLMET EXTREME-WHITENESS COMPLETE-DOCUMENT DRY RUN")
    else:
        print(
            "CLMET EXTREME-WHITENESS COMPLETE-DOCUMENT "
            "INGESTION COMPLETE"
        )

    print("=" * 72)
    print()

    print(
        f"Concordance documents:       "
        f"{len(grouped):,}"
    )

    print(
        f"Documents processed:         "
        f"{processed:,}"
    )

    print(
        f"Existing documents skipped:  "
        f"{skipped_existing:,}"
    )

    print(
        f"Missing source files:        "
        f"{missing:,}"
    )

    print(
        f"Empty/no-token documents:    "
        f"{no_text:,}"
    )

    print(
        f"Complete documents:          "
        f"{processed:,}"
    )

    print(
        f"Concordance occurrences:     "
        f"{total_concordance_occurrences:,}"
    )

    print(
        f"Complete-source tokens:      "
        f"{total_source_tokens:,}"
    )

    if not dry_run:

        print(
            f"Tokens inserted:             "
            f"{total_tokens_inserted:,}"
        )

    print(
        f"Extraction mode:             "
        f"COMPLETE SOURCE DOCUMENT"
    )

    print()
    print(
        f"Concordance:                 "
        f"{concordance_path}"
    )

    print(
        f"CLMET root:                  "
        f"{config.CLMET_CORPUS_INPUT_DIR}"
    )

    print()


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Ingest complete CLMET source documents represented in "
            "the bodily-whiteness concordance."
        )
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help=(
            "Delete all previously generated CLMET derived documents "
            "(doc_id LIKE 'CLMET3%') and their tokens before processing."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of source documents to process."
        ),
    )

    parser.add_argument(
        "--concordance",
        type=Path,
        default=CONCORDANCE_FILE,
        help=(
            "Path to bodily_whiteness_concordance.csv."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Do not write to PostgreSQL. Show the documents/tokens "
            "that would be inserted."
        ),
    )

    args = parser.parse_args()

    if args.clear:
        clear_derived_documents()

    process(
        concordance_path=args.concordance,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

