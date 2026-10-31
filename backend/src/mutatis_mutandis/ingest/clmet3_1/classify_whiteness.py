from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from lib.wordlist_whiteness import WHITENESS

INPUT = Path(
    r"d:/Downloads/clmet3_1/clmet/corpus/extreme_whiteness/"
    "bodily_whiteness_concordance.csv"
)

OUTPUT_DIR = INPUT.parent


# ---------------------------------------------------------------------------
# Lexical groups
# ---------------------------------------------------------------------------

INTENSIFIERS = {
    "very",
    "exceedingly",
    "extremely",
    "excessively",
    "perfectly",
    "pure",
    "perfect",
    "dazzling",
    "brilliant",
    "bright",
    "dead",
    "deathly",
    "ghastly",
    "intensely",
    "remarkably",
    "unusually",
    "extraordinary",
    "excessive",
}


COMPARISON = {
    "as",
    "like",
    "than",
}


RACE = {
    "negro",
    "negroes",
    "african",
    "africans",
    "black",
    "blacks",
    "race",
    "races",
}


SKIN = {
    "skin",
    "skins",
    "skinned",
    "complexion",
    "complexions",
    "flesh",
}


HAIR = {
    "hair",
    "hairs",
    "head",
    "heads",
}


EXTREME = {
    "colourless",
    "colorless",
    "colourlessness",
    "colorlessness",
    "bloodless",
    "livid",
    "cadaverous",
    "ghostly",
    "albino",
    "albinos",
    "albinoes",
    "albinism",
    "albinotic",
    "albinistic",
}


SNOW_MILK = {
    "snow",
    "snowy",
    "milk",
    "milky",
    "chalk",
}


PERSON = {
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
}



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORD_RE = re.compile(r"[A-Za-zÀ-ÿ'-]+")


def year_sort_value(year: str) -> int:
    """
    Convert CLMET's year field into a sortable integer.

    Examples:
        1730       -> 1730
        1730-1     -> 1730
        1776       -> 1776
        ""         -> 9999
    """
    if not year:
        return 9999

    match = re.match(r"(\d{4})", str(year))

    if match:
        return int(match.group(1))

    return 9999


def words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def present(tokens: set[str], vocabulary: set[str]) -> set[str]:
    return tokens & vocabulary


def nearby(tokens: list[str], vocabulary: set[str], target_index: int, radius=15):
    lo = max(0, target_index - radius)
    hi = min(len(tokens), target_index + radius + 1)

    return set(tokens[lo:hi]) & vocabulary


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

rows = []

with INPUT.open(
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        text = row["context"]
        tokens = words(text)

        if not tokens:
            continue

        token_set = set(tokens)

        whiteness_terms = present(token_set, WHITENESS)
        intensity_terms = present(token_set, INTENSIFIERS)
        race_terms = present(token_set, RACE)
        skin_terms = present(token_set, SKIN)
        hair_terms = present(token_set, HAIR)
        extreme_terms = present(token_set, EXTREME)
        snow_milk_terms = present(token_set, SNOW_MILK)
        person_terms = present(token_set, PERSON)

        categories = []

        # ---------------------------------------------------------------
        # Intensity
        # ---------------------------------------------------------------

        if intensity_terms:
            categories.append("intensity")

        # ---------------------------------------------------------------
        # Snow/milk/chalk comparisons
        # ---------------------------------------------------------------

        if snow_milk_terms:
            categories.append("snow-milk-chalk")

        # ---------------------------------------------------------------
        # Racial / ethnographic
        # ---------------------------------------------------------------

        if race_terms:
            categories.append("racial-ethnographic")

        # ---------------------------------------------------------------
        # Skin / complexion / flesh
        # ---------------------------------------------------------------

        if skin_terms:
            categories.append("skin-complexion")

        # ---------------------------------------------------------------
        # Hair
        # ---------------------------------------------------------------

        if hair_terms:
            categories.append("hair")

        # ---------------------------------------------------------------
        # Explicit extreme-description vocabulary
        # ---------------------------------------------------------------

        if extreme_terms:
            categories.append("extreme-description")

        # ---------------------------------------------------------------
        # Person
        # ---------------------------------------------------------------

        if person_terms:
            categories.append("person")

        # ---------------------------------------------------------------
        # Comparison constructions
        #
        # We only flag this when "as", "like" or "than" occurs close
        # to an actual whiteness term.
        # ---------------------------------------------------------------

        comparison_terms = set()

        for i, token in enumerate(tokens):
            if token not in WHITENESS:
                continue

            lo = max(0, i - 8)
            hi = min(len(tokens), i + 9)

            comparison_terms |= (
                set(tokens[lo:hi]) & COMPARISON
            )

        if comparison_terms:
            categories.append("comparison")

        # ---------------------------------------------------------------
        # Albino specifically
        # ---------------------------------------------------------------

        albino_terms = {
            t for t in token_set
            if t in {
                "albino",
                "albinos",
                "albinoes",
                "albinism",
                "albinotic",
                "albinistic",
            }
        }

        if albino_terms:
            categories.append("albino")

        # ---------------------------------------------------------------
        # Scoring
        #
        # This is intentionally heuristic rather than statistical.
        # It is just a prioritisation mechanism for human inspection.
        # ---------------------------------------------------------------

        score = 0

        score += len(intensity_terms) * 3
        score += len(extreme_terms) * 4
        score += len(snow_milk_terms) * 3
        score += len(race_terms) * 4
        score += len(skin_terms) * 2
        score += len(hair_terms) * 2
        score += len(comparison_terms) * 2

        if "albino" in categories:
            score += 20

        if len(categories) >= 3:
            score += 2

        if len(categories) >= 4:
            score += 3

        row["categories"] = ";".join(categories)
        row["score"] = score

        row["intensity_terms"] = ";".join(sorted(intensity_terms))
        row["race_terms"] = ";".join(sorted(race_terms))
        row["skin_terms"] = ";".join(sorted(skin_terms))
        row["hair_terms"] = ";".join(sorted(hair_terms))
        row["extreme_terms"] = ";".join(sorted(extreme_terms))
        row["snow_milk_terms"] = ";".join(sorted(snow_milk_terms))
        row["comparison_terms"] = ";".join(sorted(comparison_terms))

        rows.append(row)


# ---------------------------------------------------------------------------
# Write complete classified corpus
# ---------------------------------------------------------------------------

fields = list(rows[0].keys())

classified = OUTPUT_DIR / "bodily_whiteness_classified.csv"

with classified.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)


# ---------------------------------------------------------------------------
# Write high-value subset
# ---------------------------------------------------------------------------

interesting = [
    row for row in rows
    if row["score"] >= 6
]

interesting.sort(
    key=lambda r: (
        -int(r["score"]),
        year_sort_value(r["year"]),
    )
)

interesting_path = (
    OUTPUT_DIR / "bodily_whiteness_interesting.csv"
)

with interesting_path.open(
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(interesting)


# ---------------------------------------------------------------------------
# Category statistics
# ---------------------------------------------------------------------------

category_counts = Counter()

for row in rows:
    for category in row["categories"].split(";"):
        if category:
            category_counts[category] += 1


print()
print("=" * 72)
print("CLASSIFICATION COMPLETE")
print("=" * 72)

print()
print(f"Input contexts:       {len(rows):,}")
print(f"Interesting (score≥6): {len(interesting):,}")

print()
print("Categories:")

for category, count in category_counts.most_common():
    print(f"{category:25} {count:>8,}")

print()
print("Output:")
print(classified)
print(interesting_path)
