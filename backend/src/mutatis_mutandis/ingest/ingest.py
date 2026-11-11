#!/usr/bin/env python
"""
ingest.py - - Multi-process streaming EEBO TEI XML/text ingestion pipeline

Formerly mutatis_mutandis/tier0/tier0_0_text2db.py (formerly tier0_0_eebo_parse_tei.py)

Corpus roots are defined in config.CORPUS_INPUT_DIRS

    THE ALBINISM FILTER OF CLMET IS NOT YET APPLIED UNIVERSALLY!

"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional
import argparse
import io
import os
import re
import sys
import traceback
import unicodedata

from psycopg import sql
import xml.etree.ElementTree as etree
from lxml import etree as lxml_etree
import langdetect

import mutatis_mutandis.lib.corpus_config as config
import mutatis_mutandis.lib.corpus_db as corpus_db
import mutatis_mutandis.lib.eebo_ocr_fixes as eebo_ocr_fixes
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.wordlist_whiteness import WHITENESS, WHITENESS_WEIGHTS, WEAK_WHITENESS_PATTERNS


logger = get_logger('ingester')


MIN_WHITENESS_SCORE = 2.0

NUM_WORKERS = 4
BATCH_DOCS = 100
BATCH_TOKENS = 10000

LOG_EVERY_N_DOCS = 100
ALLOWED_PUNCT = r"\.\,\;\:\!\?\'\"\-\(\)"

# Per-worker lazy cache
_ECCO_HEADER_INDEX = None

MAX_DOCS: Optional[int] = None
SKIP_EXISTING_DOCS  = True

# Files (by name) to leave out of ingestion entirely, quietly.
SKIP_FILES: set[str] = set()

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
TEI_URI = TEI_NS["tei"]
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# Block-level elements: a space is appended after them when rendering, so
# hand-written </p><p> or </l><l> with no whitespace cannot fuse words.
BLOCK_TAGS = {"p", "l", "lg", "head", "div", "ab", "item", "sp", "speaker", "stage"}

WINDOW_WORDS = 100
WINDOW_LEFT  = WINDOW_WORDS // 2
WINDOW_RIGHT = WINDOW_WORDS - WINDOW_LEFT - 1


def whiteness_seed_score(
    tokens: list[str],
) -> tuple[int, Counter[str]]:
    hits = Counter(
        token.lower()
        for token in tokens
        if token.lower() in WHITENESS
    )

    score = sum(
        count * WHITENESS_WEIGHTS.get(lemma, 1)
        for lemma, count in hits.items()
    )

    return score, hits


def passes_whiteness_filter( doc_id: str, tokens: list[str] ) -> bool:
    score, hits = whiteness_seed_score(tokens)

    if not hits:
        return False

    seeds = set(hits)

    # White/grey/gray alone are too non-diagnostic,
    # regardless of how frequently they occur.
    if any(seeds <= weak for weak in WEAK_WHITENESS_PATTERNS):
        return False

    if score < MIN_WHITENESS_SCORE:
        return False

    logger.info( f"Whiteness filter PASS: {doc_id} score={score}, hits={dict(hits)}" )
    return True


def normalize_tei_namespace(root):
    """Put un-namespaced elements (xmlns="") into the TEI namespace."""
    for el in root.iter():
        if isinstance(el.tag, str) and not el.tag.startswith("{"):
            el.tag = f"{{{TEI_URI}}}{el.tag}"


def normalize_early_modern(text: str) -> str:
    text = text.lower()
    text = re.sub(r"(\w)[’‘ʼ′´](\w)", r"\1'\2", text)
    text = text.replace("ſ", "s")
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = re.sub(r"-\s*", " ", text)
    # I'm really not sure we ought to be messing with actual alphabetic chars
    # text = re.sub(r"\bv(?=[aeiou])", "u", text)
    # text = re.sub(r"\bj(?=[aeiou])", "i", text)
    text = re.sub(r"tv\b", "ty", text)

    text = re.sub(rf"[^{ALLOWED_PUNCT}a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_sparse_windows(
    tokens: list[str],
    left: int = WINDOW_LEFT,
    right: int = WINDOW_RIGHT,
) -> list[tuple[int, str]]:
    """
    Return (token_idx, token) pairs for every token that falls inside
    any ±window around a WHITENESS seed.  Indices are the original
    positions in the full document (sparse, not re-indexed).
    """
    if not tokens:
        return []

    hits = [
        i for i, tok in enumerate(tokens)
        if tok.lower() in WHITENESS
    ]
    if not hits:
        return []

    n = len(tokens)
    covered: set[int] = set()
    for h in hits:
        start = max(0, h - left)
        end   = min(n, h + right + 1)
        covered.update(range(start, end))

    return [(i, tokens[i]) for i in sorted(covered)]


def parse_tei(xml_path):
    """Strict parse first; fall back to lxml's recovering parser, with a warning."""
    try:
        return etree.parse(str(xml_path))
    except etree.ParseError as strict_err:
        parser = lxml_etree.XMLParser(recover=True, huge_tree=True)
        tree = lxml_etree.parse(str(xml_path), parser)
        if tree.getroot() is None:
            raise
        logger.warning(f"RECOVERED malformed XML {xml_path}: {strict_err}")
        return tree


def render_lic_text(node):
    """
    Render Literature in Context TEI into corpus text.

    Literary textual content is retained while structural, media,
    navigation, and editorial-note elements are excluded.
    """

    parts = []

    if node.text:
        parts.append(node.text)

    for child in node:
        if not isinstance(child.tag, str):   # comment / PI
            if child.tail:
                parts.append(child.tail)
            continue

        local_name = child.tag.rsplit("}", 1)[-1]

        if local_name in {
            "pb",
            "graphic",
            "note",
        }:
            # Page breaks, images, and editorial/media notes are
            # provenance or presentation material, not corpus text.
            pass

        else:
            parts.append(render_lic_text(child))
            if local_name in BLOCK_TAGS:
                parts.append(" ")

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def render_text(node):
    """Render EEBO XML into plain text while preserving editorial GAP markers."""
    parts = []

    if node.text:
        parts.append(node.text)

    for child in node:
        if not isinstance(child.tag, str):   # comment / PI (lxml recovery path)
            if child.tail:
                parts.append(child.tail)
            continue

        local_name = child.tag.rsplit("}", 1)[-1]

        if local_name == "gap":
            extent = child.attrib.get("extent", "")
            m = re.search(r"(\d+)", extent)
            n = int(m.group(1)) if m else 1
            parts.append("_" * n)

        elif (
            local_name == "note"
            and child.attrib.get("type") == "footnotelink"
        ):
            # Editorial footnote marker: do not include its content.
            pass

        else:
            parts.append(render_text(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def extract_year(date_raw: str | None):
    if not date_raw:
        return None

    m = re.search(r"\b(\d{4})\b", date_raw)

    if not m:
        return None

    return int(m.group(1))


def year_in_corpus(pub_year: int | None):
    if pub_year is None:
        return False

    return (
        config.CORPUS_MIN_YEAR
        <= pub_year
        <= config.CORPUS_MAX_YEAR
    )


def safe_text(x):
    return x.text.strip() if x is not None and x.text else None


def extract_person_name(elem):
    if elem is None:
        return None

    names = []
    for name_elem in elem.findall(".//tei:name", TEI_NS):
        fore = " ".join(
            (f.text or "").strip()
            for f in name_elem.findall("tei:forename", TEI_NS)
            if f.text and f.text.strip()
        )
        sur = " ".join(
            (s.text or "").strip()
            for s in name_elem.findall("tei:surname", TEI_NS)
            if s.text and s.text.strip()
        )
        full = f"{fore} {sur}".strip()
        if full:
            names.append(full)

    if names:
        return "; ".join(names)

    text = " ".join(" ".join(elem.itertext()).split())
    return text or None


def _year_from_date_elem(d):
    """Return (raw, year) from a TEI <date>, trying attributes then text."""
    for raw in (
        d.attrib.get("when"),
        d.attrib.get("notBefore"),
        d.attrib.get("from"),
        safe_text(d),
    ):
        y = extract_year(raw) if raw else None
        if y and y > 0:                 # rejects when="0000" template junk
            return raw, y
    return None, None


# Strongest source first. Composition dates are deliberately NOT here:
# pub_year is the date of the text as we hold it, not of the original work.
DATE_XPATHS = [
    ("publicationStmt", ".//tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:date", ),
    ("imprint",         ".//tei:teiHeader//tei:sourceDesc//tei:imprint/tei:date"),
    ("translation",     ".//tei:teiHeader//tei:sourceDesc//tei:bibl/tei:date[@type='translation']"),
    ("docDate",         ".//tei:text/tei:front//tei:docDate"),
]


def pick_pub_year(tree):
    """First usable date, strongest source first. Returns (raw, year, source)."""
    for source, xp in DATE_XPATHS:
        for d in tree.findall(xp, TEI_NS):
            raw, y = _year_from_date_elem(d)
            if y:
                return raw, y, source
    return None, None, None


def pick_composition_date(tree):
    """Original composition date as a display string, or None. Never used for pub_year."""
    d = tree.find(
        ".//tei:teiHeader//tei:;/tei:creation/tei:date", TEI_NS
    )
    if d is None:
        return None
    nb, na = d.attrib.get("notBefore"), d.attrib.get("notAfter")
    if nb or na:
        return f"{nb or '?'}-{na or '?'}"
    return d.attrib.get("when") or safe_text(d)


def to_doc_row(meta: dict) -> tuple:
    return (
        meta["corpus"],
        meta["doc_id"],
        meta["title"],
        meta["author"],
        meta["pub_year"],
        meta["publisher"],
        meta["pub_place"],
        meta["source_date_raw"],
        meta["token_count"],
        meta.get("filepath"),
        meta.get("lang"),
    )


def extract_language(tree, raw_text):
    lang_elem = tree.find(
        ".//tei:profileDesc//tei:language",
        TEI_NS,
    )

    lang = None

    if lang_elem is not None:
        lang = (
            lang_elem.attrib.get("ident")
            or safe_text(lang_elem)
        )

    if not lang:
        text_node = tree.find(".//tei:text", TEI_NS)
        if text_node is not None:
            lang = (
                text_node.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                or text_node.attrib.get("lang")
            )

    if lang:
        lang = lang.lower()

        if lang in {"eng", "en"}:
            return "eng"

        langs = re.findall(r"[a-z]{2,3}", lang)
        if langs:
            return langs[0][:3]

    try:
        detected = langdetect.detect(raw_text[:5000])
        return detected[:3] if detected else None
    except Exception:
        return None


def get_ecco_header_index():
    """
    Lazy-load ECCO header lookup on first ECCO document.
    Each worker gets its own cache.
    """
    global _ECCO_HEADER_INDEX
    if _ECCO_HEADER_INDEX is None:
        logger.info( f"[worker {os.getpid()}] loading ECCO header index" )
        _ECCO_HEADER_INDEX = {
            p.name.removesuffix(".hdr"): p
            for p in config.ECCO_HEADER_DIR.rglob("*.hdr")
        }
        logger.info( f"[worker {os.getpid()}] loaded {len(_ECCO_HEADER_INDEX)} ECCO headers" )
    return _ECCO_HEADER_INDEX


def find_ecco_header(doc_id):
    index = get_ecco_header_index()
    return index.get(doc_id)


def extract_ecco_header_metadata(header_path):
    tree = etree.parse(str(header_path))
    title = tree.findtext(".//TITLESTMT/TITLE")
    author = tree.findtext(".//TITLESTMT/AUTHOR")
    pub = tree.find(".//SOURCEDESC//PUBLICATIONSTMT")
    publisher = None
    pub_place = None
    date_raw = None
    if pub is not None:
        publisher = pub.findtext("PUBLISHER")
        pub_place = pub.findtext("PUBPLACE")
        date_raw = pub.findtext("DATE")
    year = None
    if date_raw:
        m = re.search(r"\b(\d{4})\b", date_raw)
        if m:
            year = int(m.group(1))

    return {
        "title": title,
        "author": author,
        "publisher": publisher,
        "pub_place": pub_place,
        "source_date_raw": date_raw,
        "date_raw": date_raw,
        "pub_year": year,
    }


def process_ecco_file(tree, xml_path):
    idg = tree.find(".//EEBO/IDG")

    if idg is None:
        logger.warning(f"No IDG in {xml_path}")
        return None

    doc_id = idg.attrib["ID"]

    header_path = find_ecco_header(doc_id)
    if header_path is None:
        logger.warning(f"No ECCO header for {doc_id} at {xml_path}")
        return None

    metadata = extract_ecco_header_metadata(header_path)

    pub_year = metadata["pub_year"]

    if pub_year is None:
        logger.warning(f"No pub_year in {doc_id} {xml_path}")
        return None

    if not year_in_corpus(pub_year):
        return None

    body = tree.findall(".//TEXT/BODY")

    if not body:
        logger.warning(f"No BODY for {doc_id} {xml_path}")
        return None

    raw_text = " ".join(
        render_text(b)
        for b in body
    )

    normalized = normalize_early_modern( eebo_ocr_fixes.apply_ocr_fixes(raw_text) )

    if len(normalized) < 100:
        return None

    tokens = re.findall( r"\w+|[^\w\s]", normalized )

    if not passes_whiteness_filter(doc_id, tokens):
        logger.debug( f"Rejecting {doc_id}: not enough extreme-whiteness hits" )
        return None

    if len(tokens) > config.MAX_TOKENS_IN_DOC:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"ECCO document {doc_id} has {len(tokens)} which exceeds the limit of MAX_TOKENS_IN_DOC {config.MAX_TOKENS_IN_DOC}"
        )
        return None

    lang = extract_language(tree, raw_text)

    meta = {
        "doc_id": doc_id,
        "title": metadata["title"],
        "author": metadata["author"],
        "publisher": metadata["publisher"],
        "pub_place": metadata["pub_place"],
        "pub_year": pub_year,
        "source_date_raw": metadata["date_raw"],
        "token_count": len(tokens),
        "filepath": str( xml_path.relative_to(config.CORPUS_ROOT_DIR).as_posix() ),
        "lang": lang,
    }

    return meta, tokens


def process_cme_file(tree, xml_path):
    """
    Handle University of Michigan Corpus of Middle English (CME) files.
    These use a custom <ETS> root + EEBO-like inner structure without TEI namespaces.

    TODO NB the date detection is kaput for the CME format.
    """
    root = tree.getroot()
    if root.tag != "ETS":
        logger.warning(f"Expected root <ETS>, got <{root.tag}> in {xml_path}")
        return None

    # Prefer the ID attribute on <IDG>, fall back to <IDNO TYPE="dlps">
    idg = root.find(".//IDG")
    doc_id = None
    if idg is not None:
        doc_id = idg.attrib.get("ID")

    if not doc_id:
        idno = root.find(".//IDNO[@TYPE='dlps']") or root.find(".//IDNO[@type='dlps']")
        if idno is not None and idno.text:
            doc_id = idno.text.strip()

    if not doc_id:
        doc_id = xml_path.stem
        logger.info(f"No reliable doc_id in {xml_path}; using stem {doc_id}")

    # Metadata from HEADER
    title = safe_text(root.find(".//TITLESTMT/TITLE"))
    author = safe_text(root.find(".//TITLESTMT/AUTHOR"))
    publisher = safe_text(root.find(".//PUBLICATIONSTMT/PUBLISHER"))
    pub_place = safe_text(root.find(".//PUBLICATIONSTMT/PUBPLACE"))
    date_raw = safe_text(root.find(".//PUBLICATIONSTMT/DATE"))
    pub_year = extract_year(date_raw)

    # For CME we usually want the modern transcription date for filtering,
    # but you may prefer to override or ignore the year check entirely.
    if pub_year is None:
        logger.warning(f"No pub_year for CME {doc_id} at {xml_path}")
        # return None   # uncomment if you want strict year filtering
        pub_year = 2020  # or leave as None and adjust year_in_corpus

    if pub_year is not None and not year_in_corpus(pub_year):
        # Many CME files will hit this; decide whether to keep or skip
        logger.info(f"CME {doc_id} year {pub_year} outside corpus range – keeping anyway")
        # return None

    body = root.findall(".//BODY")
    if not body:
        logger.warning(f"No BODY in CME {doc_id} at {xml_path}")
        return None

    # Re-use the existing EEBO-style renderer (handles <NOTE>, gaps, etc.)
    raw_text = " ".join(render_text(b) for b in body)

    normalized = normalize_early_modern(
        eebo_ocr_fixes.apply_ocr_fixes(raw_text)
    )

    if len(normalized) < 50:          # CME texts can be short
        logger.warning(f"CME {doc_id} too short after normalization")
        return None

    tokens = re.findall(r"\w+|[^\w\s]", normalized)

    # Language: CME source metadata may list multiple language codes.
    # The documents table stores one primary language code (CHAR(3)).
    lang_raw = "enm"
    text_elem = root.find(".//TEXT")

    if text_elem is not None:
        lang_raw = (
            text_elem.attrib.get("LANG")
            or text_elem.attrib.get("lang")
            or "enm"
        )

    langs = re.findall(r"[a-z]{2,3}", lang_raw.lower())
    lang = langs[0][:3] if langs else "enm"

    meta = {
        "doc_id": doc_id,
        "title": title,
        "author": author,
        "publisher": publisher,
        "pub_place": pub_place,
        "pub_year": pub_year,
        "source_date_raw": date_raw,
        "token_count": len(tokens),
        "filepath": str(xml_path.relative_to(config.CORPUS_ROOT_DIR).as_posix()),
        "lang": lang,
    }

    return meta, tokens


def process_misc_file(tree, xml_path):
    """
    Process generic TEI sources in the misc corpus.

    Supports LiC and other TEI sources whose document identity and
    bibliographic metadata are expressed using the standard TEI namespace.
    """

    root = tree.getroot()
    normalize_tei_namespace(root)

    root_id = root.attrib.get(XML_ID)

    if not root_id:
        root_id = xml_path.stem
        logger.info(
            f"No xml:id in {xml_path}; using filename stem {root_id!r}"
        )

    doc_id = root_id

    title_elem = tree.find(
        ".//tei:teiHeader//tei:titleStmt/tei:title",
        TEI_NS,
    )

    author_elem = tree.find(
        ".//tei:teiHeader//tei:titleStmt/tei:author",
        TEI_NS,
    )

    publisher_elem = tree.find(
        ".//tei:teiHeader//tei:sourceDesc"
        "//tei:imprint/tei:publisher",
        TEI_NS,
    )

    place_elem = tree.find(
        ".//tei:teiHeader//tei:sourceDesc"
        "//tei:imprint/tei:pubPlace",
        TEI_NS,
    )

    date_raw, pub_year, date_source = pick_pub_year(tree)
    composition_raw = pick_composition_date(tree)

    if pub_year is None:
        logger.warning( f"[worker {os.getpid()}] - No publication year in misc document {doc_id} at {xml_path}" )
        return None

    if not year_in_corpus(pub_year):
        logger.warning( f"[worker {os.getpid()}] Year not in corpus: {pub_year} for {doc_id} at {xml_path}" )
        return None

    if date_source != "imprint":
        logger.info( f"{doc_id}: year {pub_year} taken from {date_source} (no usable imprint date)" )

    source_date_raw = date_raw
    if composition_raw:
        source_date_raw = f"{date_raw} | composition {composition_raw}"

    body = tree.findall(
        ".//tei:text/tei:body",
        TEI_NS,
    )

    if not body:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"No BODY in misc document "
            f"{doc_id} at {xml_path}"
        )
        return None

    raw_text = " ".join(
        render_lic_text(b)
        for b in body
    )

    normalized = normalize_early_modern(
        eebo_ocr_fixes.apply_ocr_fixes(raw_text)
    )

    if len(normalized) < 100:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"misc document {doc_id} has normalized "
            f"text length < 100 at {xml_path}"
        )
        return None

    tokens = re.findall(
        r"\w+|[^\w\s]",
        normalized,
    )

    if len(tokens) > config.MAX_TOKENS_IN_DOC:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"misc document {doc_id} has {len(tokens)} tokens, "
            f"which exceeds MAX_TOKENS_IN_DOC "
            f"{config.MAX_TOKENS_IN_DOC}"
            "- ingesting anyway."
        )

    lang = extract_language(tree, raw_text)

    meta = {
        "doc_id": doc_id,
        "title": safe_text(title_elem),
        "author": extract_person_name(author_elem),
        "publisher": safe_text(publisher_elem),
        "pub_place": safe_text(place_elem),
        "pub_year": pub_year,
        "source_date_raw": source_date_raw,
        "token_count": len(tokens),
        "filepath": str(
            xml_path.relative_to(
                config.CORPUS_ROOT_DIR
            ).as_posix()
        ),
        "lang": lang,
    }

    return meta, tokens


# YCOE uses ASCII-compatible encodings for Old English characters.
# Replace longer sequences first (+tt before +t).
YCOE_CHAR_MAP = {
    "+tt": "ŧ",   # barred t
    "+T": "Þ",
    "+t": "þ",
    "+D": "Ð",
    "+d": "ð",
    "+A": "Æ",
    "+a": "æ",
    "+e": "ȩ",   # e-cedilla
    "vel": "ƚ",   # barred l
}

YCOE_TAG_RE = re.compile(
    r"^(?:[A-Z][A-Z0-9$+*-]*(?:\^[A-Z])?|[.,])$"
)


def decode_ycoe_form(form: str) -> str:
    """Convert YCOE/Helsinki character encodings to Unicode."""
    for encoded, unicode_char in YCOE_CHAR_MAP.items():
        form = form.replace(encoded, unicode_char)

    return form


def process_ycoe_file(pos_path: Path):
    """
    Process one YCOE POS file.

    - One file represents one Old English prose text.
    - POS tags are stripped, lexical forms are retained.
    - CODE and ID metadata are excluded.
    - Punctuation is retained.
    - Original Old English spelling and capitalisation are preserved.
    """

    try:
        raw = pos_path.read_text(encoding="ascii")
    except UnicodeDecodeError:
        logger.exception(f"YCOE file is not ASCII: {pos_path}")
        return None
    except OSError:
        logger.exception(f"Could not read YCOE file: {pos_path}")
        return None

    tokens = []
    malformed = 0

    for item in raw.split():

        # POS files encode entries as FORM_TAG.
        # rsplit is deliberate: it splits at the final underscore.
        if "_" not in item:
            malformed += 1
            continue

        form, tag = item.rsplit("_", 1)

        # These are corpus annotations, not lexical material.
        if tag in {"CODE", "ID"}:
            continue

        # Accept recognised POS tags and the punctuation tags.
        if not YCOE_TAG_RE.fullmatch(tag):
            malformed += 1
            continue

        form = decode_ycoe_form(form)

        if not form:
            continue

        tokens.append(form)

    if malformed:
        logger.debug(
            f"YCOE {pos_path.name}: ignored {malformed} "
            f"unrecognised items"
        )

    if not tokens:
        logger.warning(f"No lexical tokens extracted from {pos_path}")
        return None

    if len(tokens) > config.MAX_TOKENS_IN_DOC:
        logger.warning(
            f"YCOE document {pos_path.name} has {len(tokens)} tokens, "
            f"exceeding MAX_TOKENS_IN_DOC "
            f"{config.MAX_TOKENS_IN_DOC}"
        )
        return None

    # YCOE filename stems are stable corpus document identifiers.
    doc_id = pos_path.stem

    meta = {
        "doc_id": doc_id,
        "title": doc_id,
        "author": None,
        "publisher": None,
        "pub_place": None,

        # Do not invent a publication/composition year.
        # We can populate this later from YCOE bibliographic metadata.
        "pub_year": None,
        "source_date_raw": None,

        "token_count": len(tokens),
        "filepath": str(
            pos_path.relative_to(config.CORPUS_ROOT_DIR).as_posix()
        ),
        "lang": "ang",
    }

    logger.info(
        f"YCOE parsed {doc_id}: {len(tokens):,} tokens"
    )

    return meta, tokens


def process_eebo_file(tree, xml_path):
    doc_id_elem = tree.find(".//tei:idno[@type='DLPS']", TEI_NS)

    if doc_id_elem is None or not doc_id_elem.text:
        doc_id = Path(xml_path).stem
        logger.warning( f"process_eebo_file found no doc_id_elem {xml_path}, using {doc_id}" )
    else:
        doc_id = doc_id_elem.text.strip()

    title_elem = tree.find(".//tei:teiHeader//tei:titleStmt/tei:title", TEI_NS)
    author_elem = tree.find(".//tei:teiHeader//tei:titleStmt/tei:author", TEI_NS)
    pub_elem = tree.find(
        ".//tei:teiHeader//tei:sourceDesc//tei:publisher",
        TEI_NS,
    )
    place_elem = tree.find(
        ".//tei:teiHeader//tei:sourceDesc//tei:pubPlace",
        TEI_NS,
    )
    date_elem = tree.find(
        ".//tei:teiHeader//tei:sourceDesc//tei:date",
        TEI_NS,
    )

    date_raw = safe_text(date_elem)
    pub_year = extract_year(date_raw)

    if pub_year is None:
        logger.warning(
            f"[worker {os.getpid()}] No pub_year in {doc_id} at {xml_path}"
        )
        return None

    if not year_in_corpus(pub_year):
        return None

    body = tree.findall(".//tei:text/tei:body", TEI_NS)

    if not body:
        logger.warning(
            f"[worker {os.getpid()} ]"
            f"process_eebo_file bailing as BODY not defined in {xml_path}"
        )
        return None

    raw_text = " ".join(render_text(b) for b in body)

    normalized = normalize_early_modern(
        eebo_ocr_fixes.apply_ocr_fixes(raw_text)
    )

    if len(normalized) < config.MIN_TOKENS_IN_DOC:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"process_eebo_file bailing as normalised text length < {config.MIN_TOKENS_IN_DOC} "
            f"in {xml_path}"
        )
        return None

    lang = extract_language(tree, raw_text)

    tokens = re.findall(r"\w+|[^\w\s]", normalized)

    if len(tokens) > config.MAX_TOKENS_IN_DOC:
        logger.warning(
            f"[worker {os.getpid()}] "
            f"EEBO document {doc_id} has {len(tokens)} tokens, "
            f"which exceeds MAX_TOKENS_IN_DOC "
            f"{config.MAX_TOKENS_IN_DOC}"
        )
        return None

    meta = {
        "doc_id": doc_id,
        "title": safe_text(title_elem),
        "author": safe_text(author_elem),
        "publisher": safe_text(pub_elem),
        "pub_place": safe_text(place_elem),
        "pub_year": pub_year,
        "source_date_raw": date_raw,
        "token_count": len(tokens),
        "filepath": str(
            xml_path.relative_to(config.CORPUS_ROOT_DIR).as_posix()
        ),
        "lang": lang,
    }

    return meta, tokens


def process_file(xml_path: Path, corpus):
    # YCOE is plain-text POS, not XML.
    if corpus == "ycoe":
        return process_ycoe_file(xml_path)

    try:
        tree = parse_tei(xml_path)
    except etree.ParseError as e:
        line, col = e.position
        logger.warning(f"Failed to parse {xml_path}: {e} (line {line}, col {col})")
        return None
    except Exception as e:
        logger.warning(f"Failed to read {xml_path}: {e!r}")
        return None

    if corpus == "eebo" or corpus == "clasp":
        return process_eebo_file(tree, xml_path)
    elif corpus == "ecco":
        return process_ecco_file(tree, xml_path)
    elif corpus == "cme":
        return process_cme_file(tree, xml_path)
    elif corpus == "misc":
        return process_misc_file(tree, xml_path)
    else:
        logger.warning(f"Unknown corpus {corpus} - ignoring path {xml_path}")
        return None


def stream_copy(table: str, columns: list[str], rows):
    if not rows:
        return

    stmt = sql.SQL(
        "COPY {table} ({fields}) FROM STDIN WITH (FORMAT text, DELIMITER E'\t', NULL '\\N')"
    ).format(
        table=sql.Identifier(table),
        fields=sql.SQL(', ').join(sql.Identifier(c) for c in columns)
    )

    def encode(row):
        return "\t".join(
            "\\N" if v is None else str(v).replace("\t", " ").replace("\n", " ")
            for v in row
        ) + "\n"

    buf = io.StringIO()
    for r in rows:
        buf.write(encode(r))
    buf.seek(0)

    with corpus_db.get_autocommit_connection() as conn:
        with conn.cursor() as cur:
            with cur.copy(stmt) as copy:
                copy.write(buf.read())


# Temporary solution:
def filter_existing_docs(rows, corpus):
    if not rows:
        return []

    doc_ids = [r[1] for r in rows]

    with corpus_db.get_connection() as conn:
        cur = conn.execute(
            """
            SELECT doc_id
            FROM documents
            WHERE corpus = %s
            AND doc_id = ANY(%s)
            """,
            (corpus, doc_ids,),
        )

        existing = {r[0] for r in cur.fetchall()}

    return [
        row for row in rows
        if row[1] not in existing
    ]


def _worker_ingest(
    files,
    batch_docs,
    batch_tokens,
    skip_existing_docs,
    corpus,
    use_windows: bool = False,
):
    logger.info(f"[worker {os.getpid()}] received {len(files)} {corpus} files")

    pending = []          # list of (doc_row, token_rows)
    pending_tokens = 0
    seen_ids = set()      # guards against duplicate ids across files in this worker
    docs_seen = 0

    def flush():
        nonlocal pending, pending_tokens
        if not pending:
            return
        batch, pending, pending_tokens = pending, [], 0

        doc_rows = [d for d, _ in batch]
        if skip_existing_docs:
            keep = {r[1] for r in filter_existing_docs(doc_rows, corpus)}
            batch = [(d, t) for d, t in batch if d[1] in keep]
        if not batch:
            return

        stream_copy("documents", [
            "corpus", "doc_id", "title", "author", "pub_year",
            "publisher", "pub_place", "source_date_raw",
            "token_count", "filepath", "lang",
        ], [d for d, _ in batch])

        stream_copy("tokens", ["corpus", "doc_id", "token_idx", "token"],
                    [row for _, toks in batch for row in toks])

    for fp in files:
        try:
            result = process_file(fp, corpus)
            if not result:
                continue
            meta, tokens = result
            meta["corpus"] = corpus

            if meta["doc_id"] in seen_ids:
                new_id = f'{meta["doc_id"]}__{fp.stem}'
                logger.warning(
                    f"Duplicate doc_id {meta['doc_id']} in {fp}; using {new_id}"
                )
                meta["doc_id"] = new_id
            seen_ids.add(meta["doc_id"])

            if use_windows:
                # Force the albinism/whiteness filter for every corpus
                if not passes_whiteness_filter(meta["doc_id"], tokens):
                    logger.debug(
                        f"Rejecting {meta['doc_id']}: not enough extreme-whiteness hits"
                    )
                    continue

                windowed = extract_sparse_windows(tokens)
                if not windowed:
                    continue

                rows = [
                    (corpus, meta["doc_id"], idx, tok)
                    for idx, tok in windowed
                ]
                meta["token_count"] = len(windowed)
            else:
                # Original behaviour (ECCO already filtered inside process_ecco_file)
                rows = [
                    (corpus, meta["doc_id"], i, t)
                    for i, t in enumerate(tokens)
                ]

            pending.append((to_doc_row(meta), rows))
            pending_tokens += len(rows)
            docs_seen += 1

            if len(pending) >= batch_docs or pending_tokens >= batch_tokens:
                flush()

            if docs_seen % LOG_EVERY_N_DOCS == 0:
                logger.info(
                    f"[worker {os.getpid()}] ingested {docs_seen} docs"
                    + (" (windows)" if use_windows else "")
                )
        except Exception:
            logger.error(f"FAILED FILE: {fp}")
            logger.error(traceback.format_exc())

    try:
        flush()
    except Exception:
        logger.error(traceback.format_exc())
    logger.info(f"[worker {os.getpid()}] finished: {docs_seen} docs processed")


def resolve_input_file(file_arg: str, corpus: str) -> Path:
    """
    Locate a single input file for --file. Tries, in order: the path as given
    (absolute or relative to cwd), relative to the corpus input dir, then
    relative to CORPUS_ROOT_DIR. The file must live under CORPUS_ROOT_DIR,
    since documents.filepath is stored relative to it.
    """
    p = Path(file_arg)
    candidates = [p] if p.is_absolute() else [
        Path.cwd() / p,
        config.CORPUS_INPUT_DIRS[corpus] / p,
        config.CORPUS_ROOT_DIR / p,
    ]

    for c in candidates:
        if c.is_file():
            # abspath (not resolve) so symlinks don't break relative_to below
            found = Path(os.path.abspath(c))
            try:
                found.relative_to(config.CORPUS_ROOT_DIR)
            except ValueError:
                raise SystemExit( f"{found} is not under CORPUS_ROOT_DIR ({config.CORPUS_ROOT_DIR})" )
            return found

    raise SystemExit(
        f"--file {file_arg!r} not found. Tried:\n  "
        + "\n  ".join(str(c) for c in candidates)
    )


def ingest_file_parallel(
    input_dir: Path | None = None,
    max_workers: int      = 4,
    batch_docs: int       = 50,
    batch_tokens: int     = 50000,
    corpus: str           = None,
    doc_id: str | None    = None,
    file: Path | None     = None,
    use_windows: bool     = False,
    replace: bool         = False,
):
    if file is not None:
        input_files = [file]
    else:
        extension = ".pos" if corpus == "ycoe" else ".xml"

        input_files = [
            p for p in input_dir.rglob(f"*{extension}")
            if p.name not in SKIP_FILES
        ]

    if replace:
        if doc_id:
            # existing single-document path
            with corpus_db.get_connection(application_name="tier0-target") as conn:
                filepath = corpus_db.get_document_filepath(
                    conn, doc_id, corpus=corpus
                )
            if filepath is None:
                raise SystemExit(
                    f"Document {doc_id!r} does not exist in corpus {corpus!r}"
                )
            xml_file = Path(config.CORPUS_ROOT_DIR / Path(filepath))
            if not xml_file.is_file():
                raise FileNotFoundError(
                    f"Document {doc_id!r} is registered at {xml_file}, "
                    "but that file does not exist."
                )
            with corpus_db.get_connection(application_name="tier0-replace") as conn:
                deleted = corpus_db.delete_document(conn, doc_id, corpus=corpus)
            if not deleted:
                logger.warning(
                    "--replace requested, but document %s does not currently "
                    "exist in corpus %s", doc_id, corpus
                )
            input_files = [xml_file]

        else:
            # corpus-wide replace
            logger.warning(
                "Replacing entire corpus %r – deleting existing documents…", corpus
            )
            with corpus_db.get_connection(application_name="tier0-replace-corpus") as conn:
                deleted = corpus_db.delete_corpus_documents(conn, corpus)
            logger.info("Deleted %d documents from corpus %r", deleted, corpus)


    logger.info(f"Input directory: {input_dir}")
    logger.info(f"Found {len(input_files)} XML files")

    for x in input_files[:5]:
        logger.info(f"Example: {x}")

    if MAX_DOCS is not None:
        input_files = input_files[:MAX_DOCS]

    max_workers = max(1, min(max_workers, len(input_files)))
    chunks = [input_files[i::max_workers] for i in range(max_workers)]

    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(_worker_ingest, chunk, batch_docs, batch_tokens, SKIP_EXISTING_DOCS, corpus, use_windows )
            for chunk in chunks
        ]
        for f in futures:
            f.result()


def validate_corpus_years():
    if not isinstance(config.CORPUS_MIN_YEAR, int):
        raise TypeError("CORPUS_MIN_YEAR must be an int")
    if not isinstance(config.CORPUS_MAX_YEAR, int):
        raise TypeError("CORPUS_MAX_YEAR must be an int")
    if config.CORPUS_MIN_YEAR > config.CORPUS_MAX_YEAR:
        raise ValueError(
            "CORPUS_MIN_YEAR cannot be greater than CORPUS_MAX_YEAR"
        )
    if config.CORPUS_MIN_YEAR < 0:
        raise ValueError(f"Corpus CORPUS_MIN_YEAR appears invalid: '{config.CORPUS_MIN_YEAR}'")
    if config.CORPUS_MAX_YEAR > 2100:
        raise ValueError(f"Corpus CORPUS_MAX_YEAR appears invalid: '{config.CORPUS_MAX_YEAR}'")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to parse/add.")
    parser.add_argument("--create", action="store_true", help="Creates the database from scratch, deleting existing data. Requires manual confirmation.")
    parser.add_argument("--justindex", action="store_true", help="Does not parse any files but recreates database view and indicies.")
    parser.add_argument("--reindex", action="store_true", help="Drops and recreate indexes leading to faster ingestion of larger inputs")
    parser.add_argument( "--corpus", choices=sorted(config.CORPUS_INPUT_DIRS.keys()), default=None, help="Process only this predefined corpus.")
    parser.add_argument( "--doc-id", default=None, help="Process only the specified document ID." )
    parser.add_argument( "--replace", action="store_true", help="Replace an existing document when used with --doc-id, or corpus when used with --corpus." )
    parser.add_argument("--file", default=None, help="Ingest only this file (requires --corpus). Path may be absolute, relative to cwd, to the corpus input dir, or to CORPUS_ROOT_DIR.")
    parser.add_argument( "--windows", action="store_true", help=( "Store only sparse token windows (±50 tokens) around whiteness/albinism seed terms instead of full documents. Applies the whiteness filter to every corpus." ) )

    args = parser.parse_args()

    if args.file and not args.corpus:
        parser.error("--file requires --corpus")
    if args.file and args.doc_id:
        parser.error("--file and --doc-id are mutually exclusive")
    if args.replace and not (args.doc_id or args.corpus):
        parser.error("--replace requires --doc-id or --corpus")
    if args.doc_id and not args.corpus:
        parser.error("--doc-id requires --corpus")
    if args.replace and args.file:
        parser.error("--replace cannot be combined with --file; use --doc-id instead")

    validate_corpus_years() # Eventually allow flags

    global MAX_DOCS, SKIP_EXISTING_DOCS
    MAX_DOCS           = args.limit
    SKIP_EXISTING_DOCS = not (args.create or args.replace)

    target_file = resolve_input_file(args.file, args.corpus) if args.file else None

    with corpus_db.get_connection() as conn:
        if args.create:
            confirm = input("DESTROY DB? type YES: ")
            if confirm != "YES":
                sys.exit(1)
            corpus_db.init_db(conn)
            corpus_db.create_views(conn)

        if args.reindex:
            corpus_db.drop_token_indexes(conn)
            corpus_db.drop_tokens_fk(conn)

        conn.commit()

    if args.justindex:
        logger.info("=== Just indexing the DB, not parsing or ingesting files ===")
    else:
        corpora = (
            {args.corpus: config.CORPUS_INPUT_DIRS[args.corpus]}
            if args.corpus
            else config.CORPUS_INPUT_DIRS
        )

        for corpus, input_dir in corpora.items():
            logger.info(f"Process {corpus} from {input_dir}")

            if not input_dir.is_dir():
                parser.error( f"Input directory for {corpus} does not exist: {input_dir}" )

            ingest_file_parallel(
                input_dir      = input_dir,
                max_workers  = NUM_WORKERS,
                batch_docs   = BATCH_DOCS,
                batch_tokens = BATCH_TOKENS,
                corpus       = corpus,
                doc_id       = args.doc_id,
                file         = target_file,
                use_windows  = args.windows,
                replace      = args.replace,
            )

    # ------------------------------------------------------------------
    # Conventional publication years for YCOE (only when we touched it)
    # ------------------------------------------------------------------
    ycoe_was_processed = (
        not args.justindex
        and (
            args.corpus == "ycoe"
            or (args.corpus is None and "ycoe" in config.CORPUS_INPUT_DIRS)
        )
    )

    if ycoe_was_processed:
        logger.info("Applying conventional publication years for YCOE documents as YCOE metadata still not processed")
        with corpus_db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documents
                    SET pub_year = CASE
                        -- Alfredian / early West Saxon
                        WHEN doc_id LIKE 'cocura%'          THEN 890
                        WHEN doc_id LIKE 'cobede%'          THEN 900
                        WHEN doc_id LIKE 'cogregd%'         THEN 900

                        -- Ælfric
                        WHEN doc_id LIKE 'cocathom%'        THEN 995
                        WHEN doc_id LIKE 'coaelive%'        THEN 1000
                        WHEN doc_id LIKE 'coaelhom%'        THEN 1005

                        -- Other named authors / works
                        WHEN doc_id LIKE 'cobyrhtf%'        THEN 1015
                        WHEN doc_id LIKE 'cochron%'         THEN 1000
                        WHEN doc_id LIKE 'colaw%'           THEN 1020
                        WHEN doc_id LIKE 'colaece%'
                          OR doc_id LIKE 'colacnu%'        THEN 1050

                        -- Saints’ lives / dialogues / miscellaneous OE
                        WHEN doc_id LIKE 'coapollo%'        THEN 1000
                        WHEN doc_id LIKE 'coaugust%'        THEN 1000
                        WHEN doc_id LIKE 'coadrian%'        THEN 1000
                        WHEN doc_id LIKE 'coalcuin%'        THEN 900
                        WHEN doc_id LIKE 'coalex%'          THEN 1000
                        WHEN doc_id LIKE 'cobenrul%'        THEN 1000
                        WHEN doc_id LIKE 'coblick%'         THEN 1000
                        WHEN doc_id LIKE 'coboeth%'         THEN 900
                        WHEN doc_id LIKE 'cocanedg%'        THEN 1000
                        WHEN doc_id LIKE 'cochad%'          THEN 1000
                        WHEN doc_id LIKE 'cochdrul%'        THEN 1000
                        WHEN doc_id LIKE 'cochristoph%'     THEN 1000
                        WHEN doc_id LIKE 'codicts%'         THEN 1000
                        WHEN doc_id LIKE 'codocu%'          THEN 1000
                        WHEN doc_id LIKE 'coeluc%'          THEN 1000
                        WHEN doc_id LIKE 'coepigen%'        THEN 1000
                        WHEN doc_id LIKE 'coeuphr%'         THEN 1000
                        WHEN doc_id LIKE 'coeust%'          THEN 1000
                        WHEN doc_id LIKE 'coexodus%'        THEN 1000
                        WHEN doc_id LIKE 'cogenesi%'        THEN 1000
                        WHEN doc_id LIKE 'coherbar%'        THEN 1050
                        WHEN doc_id LIKE 'coinspol%'        THEN 1000
                        WHEN doc_id LIKE 'cojames%'         THEN 1000

                        -- Fallback for any remaining YCOE texts
                        WHEN corpus = 'ycoe'                THEN 1000
                        ELSE pub_year
                    END
                    WHERE pub_year IS NULL
                      AND corpus = 'ycoe'
                """)
            conn.commit()

    with corpus_db.get_connection() as conn:
        if args.reindex:
            corpus_db.create_tokens_fk(conn)
            corpus_db.create_token_indexes(conn)

if __name__ == "__main__":
    main()
