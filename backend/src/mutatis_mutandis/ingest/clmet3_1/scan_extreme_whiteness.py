from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from lib.wordlist_whiteness import WHITENESS

VRT = Path(r"d:/Downloads/clmet3_1/clmet/corpus/clmet.vrt")
OUT_DIR = VRT.parent / "extreme_whiteness"

OUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Lexical field
# ---------------------------------------------------------------------------


BODY = {
    "skin",
    "skins",
    "skinned",
    "complexion",
    "complexions",
    "face",
    "faces",
    "visage",
    "visages",
    "countenance",
    "countenances",
    "body",
    "bodies",
    "flesh",
    "hair",
    "hairs",
    "head",
    "heads",

    # people
    "person",
    "persons",
    "man",
    "men",
    "woman",
    "women",
    "child",
    "children",
    "boy",
    "boys",
    "girl",
    "girls",

    # particularly relevant historical racial contexts
    "negro",
    "negroes",
    "black",
    "blacks",
    "african",
    "africans",

    # other visible bodily features
    "eye",
    "eyes",
    "brow",
    "brows",
    "cheek",
    "cheeks",
    "lip",
    "lips",
    "blood",
}


# Strong intensifiers / comparison constructions.
INTENSIFIERS = {
    "very",
    "exceedingly",
    "extremely",
    "excessively",
    "perfectly",
    "pure",
    "perfect",
    "deadly",
    "deathly",
    "dead",
    "ghastly",
    "dazzling",
    "brilliant",
    "bright",
    "snow",
    "snowy",
    "milk",
    "milky",
    "chalk",
}


WINDOW = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ATTRIBUTE_RE = re.compile(r'(\w+)="([^"]*)"')


def metadata_from_text_tag(line: str) -> dict[str, str]:
    return dict(ATTRIBUTE_RE.findall(line))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Output 1: lexical frequencies
# ---------------------------------------------------------------------------

frequency = Counter()


# ---------------------------------------------------------------------------
# Output 2: candidate contexts
# ---------------------------------------------------------------------------

contexts: list[dict] = []

current_meta: dict[str, str] = {}

# Tokens in the current sentence.
sentence: list[tuple[str, str, str, str]] = []

# Sentence number within document.
sentence_number = 0


def process_sentence() -> None:
    """Process the completed sentence."""

    global sentence_number

    if not sentence:
        return

    sentence_number += 1

    # Lowercase lemma lookup.
    lemmas = [token[2].lower() for token in sentence]

    whiteness_positions = [
        i for i, lemma in enumerate(lemmas)
        if lemma in WHITENESS
    ]

    if not whiteness_positions:
        return

    body_positions = [
        i for i, lemma in enumerate(lemmas)
        if lemma in BODY
    ]

    for wi in whiteness_positions:

        nearby_body = [
            bi for bi in body_positions
            if abs(bi - wi) <= WINDOW
        ]

        if not nearby_body:
            continue

        # Look for intensity/comparison vocabulary near the
        # whiteness term.
        nearby_intensifiers = [
            sentence[i][0]
            for i in range(
                max(0, wi - WINDOW),
                min(len(sentence), wi + WINDOW + 1),
            )
            if sentence[i][2].lower() in INTENSIFIERS
        ]

        left = sentence[max(0, wi - WINDOW):wi]
        right = sentence[wi + 1:min(len(sentence), wi + WINDOW + 1)]

        context_text = " ".join(
            token[0]
            for token in sentence
        )

        contexts.append({
            "document_id": current_meta.get("id", ""),
            "file": current_meta.get("file", ""),
            "period": current_meta.get("period", ""),
            "quartcent": current_meta.get("quartcent", ""),
            "decade": current_meta.get("decade", ""),
            "year": current_meta.get("year", ""),
            "genre": current_meta.get("genre", ""),
            "subgenre": current_meta.get("subgenre", ""),
            "title": current_meta.get("title", ""),
            "author": current_meta.get("author", ""),
            "gender": current_meta.get("gender", ""),
            "author_birth": current_meta.get("author_birth", ""),

            "sentence_number": sentence_number,

            "whiteness_surface": sentence[wi][0],
            "whiteness_lemma": sentence[wi][2],

            "body_terms": ";".join(
                sorted(
                    {
                        sentence[bi][2]
                        for bi in nearby_body
                    }
                )
            ),

            "intensifiers": ";".join(
                sorted(set(nearby_intensifiers))
            ),

            "context": context_text,
        })


# ---------------------------------------------------------------------------
# Scan VRT
# ---------------------------------------------------------------------------

print(f"Scanning: {VRT}")
print("This is a single streaming pass over the VRT...")
print()

with VRT.open("r", encoding="utf-8") as f:

    for line_no, line in enumerate(f, 1):
        line = line.rstrip("\n")

        # ---------------------------------------------------------------
        # Document
        # ---------------------------------------------------------------

        if line.startswith("<text "):
            current_meta = metadata_from_text_tag(line)
            sentence = []
            sentence_number = 0
            continue

        if line == "</text>":
            process_sentence()
            sentence = []
            current_meta = {}
            continue

        # ---------------------------------------------------------------
        # Sentence boundary
        # ---------------------------------------------------------------

        if line == "</s>":
            process_sentence()
            sentence = []
            continue

        if line.startswith("<"):
            continue

        # ---------------------------------------------------------------
        # Token
        # ---------------------------------------------------------------

        parts = line.split("\t")

        if len(parts) < 4:
            continue

        word, pos, lemma, wordclass = parts[:4]

        lemma_lower = lemma.lower()

        # Frequency count.
        if lemma_lower in WHITENESS:
            frequency[lemma_lower] += 1

        sentence.append(
            (
                word,
                pos,
                lemma,
                wordclass,
            )
        )


# ---------------------------------------------------------------------------
# Write frequency table
# ---------------------------------------------------------------------------

frequency_rows = [
    {
        "lemma": lemma,
        "frequency": count,
    }
    for lemma, count in frequency.most_common()
]

write_csv(
    OUT_DIR / "whiteness_lexical_frequencies.csv",
    frequency_rows,
    ["lemma", "frequency"],
)


# ---------------------------------------------------------------------------
# Write contextual concordance
# ---------------------------------------------------------------------------

context_fields = [
    "document_id",
    "file",
    "period",
    "quartcent",
    "decade",
    "year",
    "genre",
    "subgenre",
    "title",
    "author",
    "gender",
    "author_birth",
    "sentence_number",
    "whiteness_surface",
    "whiteness_lemma",
    "body_terms",
    "intensifiers",
    "context",
]

write_csv(
    OUT_DIR / "bodily_whiteness_concordance.csv",
    contexts,
    context_fields,
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 72)
print("DONE")
print("=" * 72)

print()
print("Lexical frequencies:")
for row in frequency_rows:
    print(f"{row['lemma']:20} {row['frequency']:>8,}")

print()
print(f"Bodily-whiteness contexts: {len(contexts):,}")

print()
print("Output:")
print(OUT_DIR / "whiteness_lexical_frequencies.csv")
print(OUT_DIR / "bodily_whiteness_concordance.csv")
