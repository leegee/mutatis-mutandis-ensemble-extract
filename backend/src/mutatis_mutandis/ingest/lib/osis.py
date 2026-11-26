"""OSIS Bible ingestion helpers.

This module deliberately has no dependency on the main ingest.py module.
It returns one (metadata, tokens) record per verse so that biblical
references remain addressable in the existing document/token schema.

Expected source layout is OSIS XML with a default namespace, for example:
    <div type="book" osisID="Lam">
      <chapter osisID="Lam.4">
        <verse osisID="Lam.4.7">...</verse>
      </chapter>
    </div>

The parser also tolerates an unnamespaced OSIS document. It handles the
explicit <verse osisID="..."> form used by gratis-bible's split KJV files.
It does not attempt to interpret OSIS milestone-style verse boundaries.
"""

from __future__ import annotations

from pathlib import Path
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

OSIS_NS = "http://www.bibletechnologies.net/2003/OSIS/namespace"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# OSIS book identifiers -> readable names. Unknown identifiers are retained.
BOOK_NAMES = {
    "Gen": "Genesis", "Exod": "Exodus", "Lev": "Leviticus",
    "Num": "Numbers", "Deut": "Deuteronomy", "Josh": "Joshua",
    "Judg": "Judges", "Ruth": "Ruth", "1Sam": "1 Samuel",
    "2Sam": "2 Samuel", "1Kgs": "1 Kings", "2Kgs": "2 Kings",
    "1Chr": "1 Chronicles", "2Chr": "2 Chronicles", "Ezra": "Ezra",
    "Neh": "Nehemiah", "Esth": "Esther", "Job": "Job",
    "Ps": "Psalms", "Prov": "Proverbs", "Eccl": "Ecclesiastes",
    "Song": "Song of Solomon", "Isa": "Isaiah", "Jer": "Jeremiah",
    "Lam": "Lamentations", "Ezek": "Ezekiel", "Dan": "Daniel",
    "Hos": "Hosea", "Joel": "Joel", "Amos": "Amos", "Obad": "Obadiah",
    "Jonah": "Jonah", "Mic": "Micah", "Nah": "Nahum", "Hab": "Habakkuk",
    "Zeph": "Zephaniah", "Hag": "Haggai", "Zech": "Zechariah",
    "Mal": "Malachi", "Matt": "Matthew", "Mark": "Mark",
    "Luke": "Luke", "John": "John", "Acts": "Acts",
    "Rom": "Romans", "1Cor": "1 Corinthians", "2Cor": "2 Corinthians",
    "Gal": "Galatians", "Eph": "Ephesians", "Phil": "Philippians",
    "Col": "Colossians", "1Thess": "1 Thessalonians",
    "2Thess": "2 Thessalonians", "1Tim": "1 Timothy",
    "2Tim": "2 Timothy", "Titus": "Titus", "Phlm": "Philemon",
    "Heb": "Hebrews", "Jas": "James", "1Pet": "1 Peter",
    "2Pet": "2 Peter", "1John": "1 John", "2John": "2 John",
    "3John": "3 John", "Jude": "Jude", "Rev": "Revelation",
}

TRANSLATION_METADATA = {
    "kjv": {
        "title": "King James Version",
        "pub_year": 1611,
        "author": None,
        "publisher": "FREE BIBLE SOFTWARE GROUP",
        "source_date_raw": (
            "KJV first published in 1611; "
            "OSIS work date: 2009-01-23; "
            "revision date: 2010-02-26"
        ),
    },
}


def _local_name(tag: str) -> str:
    """Return an XML local name, regardless of namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _normalise_text(text: str) -> str:
    """Match ingest.py's Unicode normalisation without applying OCR fixes."""
    text = unicodedata.normalize("NFC", text).lower()
    text = text.translate(str.maketrans({"\u2018": "'", "\u2019": "'", "\u02bc": "'"}))
    text = "".join(
        ch if unicodedata.category(ch)[0] in {"L", "M", "N", "P"} or ch.isspace()
        else " "
        for ch in text
    )
    return re.sub(r"\s+", " ", text).strip()


def _element_text(elem: ET.Element) -> str:
    """Collect all textual content, including nested inline OSIS markup."""
    return " ".join("".join(elem.itertext()).split())


def _relative_path(path: Path, corpus_root: Path | None) -> str:
    path = path.resolve()
    if corpus_root is not None:
        try:
            return path.relative_to(Path(corpus_root).resolve()).as_posix()
        except ValueError:
            logger.warning("OSIS file %s is outside corpus root %s", path, corpus_root)
    return path.as_posix()


def _find_osis_text(root: ET.Element) -> ET.Element | None:
    if _local_name(root.tag) == "osisText":
        return root
    for elem in root.iter():
        if _local_name(elem.tag) == "osisText":
            return elem
    return None


def process_osis_file(
    xml_path: str | Path,
    corpus_root: str | Path | None = None,
) -> list[tuple[dict, list[str]]]:
    """Parse an OSIS book file into one ingest record per verse.

    Returns:
        [(meta, tokens), ...]

    `doc_id` is stable and reversible, e.g. ``kjv_Lam_4_7``; the canonical
    OSIS reference is also retained in ``meta['osis_ref']`` and the title.
    `pub_year` is deliberately ignored: this source's OSIS work/revision dates
    are not the publication date of the KJV edition represented by its text.
    See the default metadata.
    """
    path = Path(xml_path)
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        logger.warning("Could not parse OSIS file %s: %s", path, exc)
        return []

    root = tree.getroot()
    osis_text = _find_osis_text(root)
    if osis_text is None:
        logger.warning("No <osisText> element in OSIS file %s", path)
        return []

    work_id = osis_text.attrib.get("osisIDWork", "kjv").strip() or "kjv"
    language = (
        osis_text.attrib.get(XML_LANG)
        or osis_text.attrib.get("lang")
        or "en"
    )

    header = next((e for e in osis_text if _local_name(e.tag) == "header"), None)
    work = None
    if header is not None:
        work = next((e for e in header if _local_name(e.tag) == "work"), None)

    translation_title = "King James Version"
    publisher = None
    work_date = None
    revision_date = None
    if work is not None:
        for child in work:
            name = _local_name(child.tag)
            value = _element_text(child)
            if name == "title" and value:
                translation_title = value
            elif name == "publisher" and value:
                publisher = value
            elif name == "date" and value and work_date is None:
                work_date = value
    if header is not None:
        revision = next((e for e in header if _local_name(e.tag) == "revisionDesc"), None)
        if revision is not None:
            date_elem = next((e for e in revision if _local_name(e.tag) == "date"), None)
            if date_elem is not None:
                revision_date = _element_text(date_elem) or None

    source_date_parts = []
    if work_date:
        source_date_parts.append(f"OSIS work date: {work_date}")
    if revision_date:
        source_date_parts.append(f"OSIS revision date: {revision_date}")
    source_date_raw = "; ".join(source_date_parts) or None

    books = [
        elem for elem in osis_text.iter()
        if _local_name(elem.tag) == "div" and elem.attrib.get("type") == "book"
    ]
    if not books:
        logger.warning("No <div type='book'> elements in OSIS file %s", path)
        return []

    records: list[tuple[dict, list[str]]] = []
    seen_refs: set[str] = set()

    for book_elem in books:
        book_id = book_elem.attrib.get("osisID", "").strip()
        if not book_id:
            logger.warning("OSIS book div without osisID in %s", path)
            continue
        book_name = BOOK_NAMES.get(book_id, book_id)

        chapters = [e for e in book_elem.iter() if _local_name(e.tag) == "chapter"]
        for chapter_elem in chapters:
            chapter_id = chapter_elem.attrib.get("osisID", "").strip()
            chapter_match = re.fullmatch(rf"{re.escape(book_id)}\.(\d+)", chapter_id)
            if not chapter_match:
                logger.warning("Unexpected OSIS chapter ID %r in %s", chapter_id, path)
                continue
            chapter_num = chapter_match.group(1)

            verses = [e for e in chapter_elem.iter() if _local_name(e.tag) == "verse"]
            for verse_elem in verses:
                osis_ref = verse_elem.attrib.get("osisID", "").strip()
                match = re.fullmatch(
                    rf"{re.escape(book_id)}\.{re.escape(chapter_num)}\.(\d+(?:[a-z])?)",
                    osis_ref,
                    flags=re.IGNORECASE,
                )
                if not match:
                    logger.warning("Unexpected or missing OSIS verse ID %r in %s", osis_ref, path)
                    continue
                if osis_ref in seen_refs:
                    logger.warning("Duplicate OSIS verse ID %s in %s", osis_ref, path)
                    continue
                seen_refs.add(osis_ref)

                verse_num = match.group(1)
                raw_text = _element_text(verse_elem)
                normalized = _normalise_text(raw_text)
                if not normalized:
                    logger.debug("Skipping empty OSIS verse %s in %s", osis_ref, path)
                    continue

                tokens = re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE)
                if not tokens:
                    continue

                doc_id = f"{work_id}_{osis_ref.replace('.', '_')}"
                title = f"{translation_title} — {book_name} {chapter_num}:{verse_num} [{osis_ref}]"
                meta = {
                    "doc_id": doc_id,
                    "title": title,
                    "author": None,
                    "publisher": publisher,
                    "pub_place": None,
                    "pub_year": None,
                    "source_date_raw": source_date_raw,
                    "token_count": len(tokens),
                    "filepath": _relative_path(path, Path(corpus_root) if corpus_root else None),
                    "lang": language[:3].lower(),
                    "osis_ref": osis_ref,
                    "book_id": book_id,
                    "chapter": int(chapter_num),
                    "verse": verse_num,
                    "translation_id": work_id,
                } | TRANSLATION_METADATA[work_id]

                records.append((meta, tokens))

    if not records:
        logger.warning("No explicit OSIS verses extracted from %s", path)
    else:
        logger.info("OSIS parsed %s: %s verses", path, f"{len(records):,}")

    return records
