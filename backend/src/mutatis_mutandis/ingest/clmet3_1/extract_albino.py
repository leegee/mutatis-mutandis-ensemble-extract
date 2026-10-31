from pathlib import Path
import csv
import re

VRT = Path("d:/Downloads/clmet3_1/clmet/corpus/clmet.vrt")
OUT = Path("d:/Downloads/clmet3_1/clmet/corpus/albino_hits.csv")

# Anything whose lemma begins "albin".
# This catches:
#   albino
#   albinos
#   albinoes
#   albinism
#   albinotic
# etc.
TARGET = re.compile(r"^albin", re.IGNORECASE)

# Number of tokens either side of the hit.
CONTEXT = 75


def parse_metadata(line):
    """Parse attributes from <text ...>."""
    return dict(
        re.findall(r'(\w+)="([^"]*)"', line)
    )


def token_text(tokens):
    """Reconstruct readable text from VRT tokens."""
    return " ".join(token[0] for token in tokens)


hits = []

current_meta = None
current_tokens = []

with VRT.open("r", encoding="utf-8") as f:

    for line_no, line in enumerate(f, 1):
        line = line.rstrip("\n")

        # ------------------------------------------------------------
        # New document
        # ------------------------------------------------------------
        if line.startswith("<text "):
            current_meta = parse_metadata(line)
            current_tokens = []
            continue

        # ------------------------------------------------------------
        # End document
        # ------------------------------------------------------------
        if line == "</text>":
            current_meta = None
            current_tokens = []
            continue

        # ------------------------------------------------------------
        # Ignore XML structure
        # ------------------------------------------------------------
        if line.startswith("<"):
            continue

        # ------------------------------------------------------------
        # Token
        # ------------------------------------------------------------
        parts = line.split("\t")

        if len(parts) < 4:
            continue

        word, pos, lemma, wordclass = parts[:4]

        index = len(current_tokens)

        current_tokens.append(
            (word, pos, lemma, wordclass)
        )

        # ------------------------------------------------------------
        # Target
        # ------------------------------------------------------------
        if not TARGET.match(lemma):
            continue

        left = current_tokens[
            max(0, index - CONTEXT):index
        ]

        # We don't yet know the right context, so store the
        # document + token position and deal with it later.
        hits.append({
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
            "surface": word,
            "lemma": lemma,
            "pos": pos,
            "wordclass": wordclass,
            "vrt_line": line_no,
            "token_index": index,
        })


# --------------------------------------------------------------------
# Write initial hit list
# --------------------------------------------------------------------

fields = [
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
    "surface",
    "lemma",
    "pos",
    "wordclass",
    "vrt_line",
    "token_index",
]

with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(hits)

print(f"Found {len(hits):,} hits")
print(f"Wrote {OUT}")
