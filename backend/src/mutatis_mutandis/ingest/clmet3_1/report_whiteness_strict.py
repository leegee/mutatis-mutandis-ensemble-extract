from __future__ import annotations

import csv
import re
from pathlib import Path


INPUT = Path(
    r"d:/Downloads/clmet3_1/clmet/corpus/extreme_whiteness/"
    "bodily_whiteness_concordance.csv"
)

OUT_DIR = INPUT.parent


# ---------------------------------------------------------------------------
# Lexical sets
# ---------------------------------------------------------------------------

WHITE = {
    "white",
    "whiteness",
    "whiten",
    "whitened",
    "whitening",
}

PALE = {
    "pale",
    "paleness",
    "pallid",
    "pallor",
    "wan",
    "wanly",
    "wanness",
}

GREY = {
    "grey",
    "gray",
    "greyness",
    "grayness",
    "hoary",
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

BODY_SKIN = {
    "skin",
    "skins",
    "skinned",
    "complexion",
    "complexions",
    "flesh",
    "face",
    "faces",
    "visage",
    "visages",
    "countenance",
    "countenances",
}

BODY_HAIR = {
    "hair",
    "hairs",
    "head",
    "heads",
    "beard",
    "beards",
    "lock",
    "locks",
    "tress",
    "tresses",
}

BODY_OTHER = {
    "lip",
    "lips",
    "mouth",
    "eye",
    "eyes",
    "brow",
    "brows",
    "cheek",
    "cheeks",
    "forehead",
    "neck",
    "hand",
    "hands",
    "arm",
    "arms",
    "body",
    "bodies",
    "flesh",
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
    "infant",
    "infants",
}

ETHNIC = {
    "negro",
    "negroes",
    "african",
    "africans",
    "ethiopian",
    "ethiopians",
    "race",
    "races",
}

INTENSIFIERS = {
    "very",
    "exceedingly",
    "extremely",
    "excessively",
    "perfectly",
    "pure",
    "purely",
    "remarkably",
    "extraordinarily",
    "extraordinary",
    "unusually",
    "incredibly",
    "intensely",
    "dazzling",
    "brilliant",
    "bright",
    "dead",
    "deathly",
    "ghastly",
    "perfect",
}

COMPARISON_MARKERS = {
    "as",
    "like",
    "than",
}

COMPARISON_OBJECTS = {
    "snow",
    "snowy",
    "milk",
    "milky",
    "chalk",
    "marble",
    "ivory",
    "alabaster",
    "ghost",
    "ghosts",
    "death",
    "dead",
    "corpse",
    "corpses",
    "paper",
    "linen",
    "wax",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORD_RE = re.compile(r"[A-Za-zÀ-ÿ'-]+")


def tokens(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def nearby(
    toks: list[str],
    target: int,
    vocabulary: set[str],
    radius: int,
) -> set[str]:

    lo = max(0, target - radius)
    hi = min(len(toks), target + radius + 1)

    return {
        toks[i]
        for i in range(lo, hi)
        if toks[i] in vocabulary
    }


def has_adjacent_or_near(
    toks: list[str],
    source: set[str],
    target: set[str],
    radius: int = 4,
) -> tuple[bool, set[str], set[str]]:

    source_hits = set()
    target_hits = set()

    for i, token in enumerate(toks):

        if token not in source:
            continue

        for j in range(
            max(0, i - radius),
            min(len(toks), i + radius + 1),
        ):
            if toks[j] in target:
                source_hits.add(token)
                target_hits.add(toks[j])

    return bool(source_hits and target_hits), source_hits, target_hits


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

with INPUT.open(
    "r",
    encoding="utf-8-sig",
    newline="",
) as f:

    source_rows = list(csv.DictReader(f))


classified = []


for row in source_rows:

    text = row["context"]
    toks = tokens(text)

    if not toks:
        continue

    categories: set[str] = set()

    matched_white = set()
    matched_pale = set()
    matched_grey = set()
    matched_extreme = set()

    matched_skin = set()
    matched_hair = set()
    matched_other_body = set()

    matched_intensity = set()
    matched_comparison = set()
    matched_comparison_objects = set()
    matched_ethnic = set()

    # ================================================================
    # 1. Explicit albino anchor
    # ================================================================

    albino_terms = {
        t for t in toks
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
        categories.add("albino")
        matched_extreme |= albino_terms


    # ================================================================
    # 2. Extreme bodily descriptors
    #
    # These are inherently interesting when they occur near a body
    # term. Unlike "white", words such as colourless/bloodless/
    # cadaverous are already relatively marked.
    # ================================================================

    extreme_positions = [
        i for i, t in enumerate(toks)
        if t in EXTREME
    ]

    for i in extreme_positions:

        for j in range(
            max(0, i - 5),
            min(len(toks), i + 6),
        ):

            if toks[j] in BODY_SKIN | BODY_OTHER | PERSON:
                categories.add("extreme-description")
                matched_extreme.add(toks[i])


    # ================================================================
    # 3. White/pale + skin/face/complexion/etc.
    #
    # Tight local association: maximum 4 tokens.
    # ================================================================

    ok, a, b = has_adjacent_or_near(
        toks,
        WHITE | PALE,
        BODY_SKIN | BODY_OTHER,
        radius=4,
    )

    if ok:
        categories.add("bodily-whiteness")
        matched_white |= a & WHITE
        matched_pale |= a & PALE

        # Record the actual bodily terms.
        matched_skin |= b & BODY_SKIN
        matched_other_body |= b & BODY_OTHER


    # ================================================================
    # 4. White/pale + person
    #
    # Slightly weaker than direct body descriptions.
    # ================================================================

    ok, a, b = has_adjacent_or_near(
        toks,
        WHITE | PALE,
        PERSON,
        radius=4,
    )

    if ok:
        categories.add("person-whiteness")
        matched_white |= a & WHITE
        matched_pale |= a & PALE


    # ================================================================
    # 5. Hair whiteness
    #
    # Keep grey/gray/hoary here, but DON'T count it as extreme
    # whiteness by itself.
    # ================================================================

    ok, a, b = has_adjacent_or_near(
        toks,
        WHITE | PALE | GREY,
        BODY_HAIR,
        radius=4,
    )

    if ok:
        categories.add("hair-whiteness")

        matched_white |= a & WHITE
        matched_pale |= a & PALE
        matched_grey |= a & GREY
        matched_hair |= b & BODY_HAIR


    # ================================================================
    # 6. Intensity
    #
    # Only count an intensifier when it is close to a whiteness
    # expression, rather than anywhere in the sentence.
    # ================================================================

    for i, token in enumerate(toks):

        if token not in WHITE | PALE | EXTREME:
            continue

        hits = nearby(
            toks,
            i,
            INTENSIFIERS,
            radius=4,
        )

        if hits:
            categories.add("intensified")
            matched_intensity |= hits


    # ================================================================
    # 7. Explicit comparisons
    #
    # e.g. white as snow
    #      pale as death
    #      white like marble
    # ================================================================

    for i, token in enumerate(toks):

        if token not in WHITE | PALE:
            continue

        lo = max(0, i - 4)
        hi = min(len(toks), i + 5)

        local = toks[lo:hi]

        if not any(
            marker in local
            for marker in COMPARISON_MARKERS
        ):
            continue

        objects = {
            x for x in local
            if x in COMPARISON_OBJECTS
        }

        if objects:
            categories.add("explicit-comparison")
            matched_comparison |= (
                set(local) & COMPARISON_MARKERS
            )
            matched_comparison_objects |= objects


    # ================================================================
    # 8. Ethnographic context
    #
    # Flag only when ethnic terminology occurs close to an actual
    # bodily whiteness expression.
    # ================================================================

    ethnic_positions = [
        i for i, t in enumerate(toks)
        if t in ETHNIC
    ]

    for ei in ethnic_positions:

        lo = max(0, ei - 8)
        hi = min(len(toks), ei + 9)

        local = toks[lo:hi]

        if any(
            t in WHITE | PALE | EXTREME
            for t in local
        ):
            categories.add("ethnographic")
            matched_ethnic.add(toks[ei])


    # ================================================================
    # 9. Construct a simple evidence score
    #
    # This is now based on actual constructions, not arbitrary
    # co-occurrence.
    # ================================================================

    score = 0

    if "albino" in categories:
        score += 20

    if "extreme-description" in categories:
        score += 8

    if "bodily-whiteness" in categories:
        score += 6

    if "person-whiteness" in categories:
        score += 3

    if "hair-whiteness" in categories:
        score += 2

    if "intensified" in categories:
        score += 4

    if "explicit-comparison" in categories:
        score += 4

    if "ethnographic" in categories:
        score += 3

    # Multiple independent signals.
    if len(categories) >= 3:
        score += 2

    if len(categories) >= 4:
        score += 2


    # ================================================================
    # Keep only actual evidence categories.
    # ================================================================

    if not categories:
        continue

    row = dict(row)

    row["strict_categories"] = ";".join(sorted(categories))
    row["strict_score"] = score

    row["matched_white"] = ";".join(sorted(matched_white))
    row["matched_pale"] = ";".join(sorted(matched_pale))
    row["matched_grey"] = ";".join(sorted(matched_grey))
    row["matched_extreme"] = ";".join(sorted(matched_extreme))

    row["matched_skin"] = ";".join(sorted(matched_skin))
    row["matched_hair"] = ";".join(sorted(matched_hair))
    row["matched_body"] = ";".join(
        sorted(
            matched_skin |
            matched_other_body
        )
    )

    row["matched_intensity"] = ";".join(
        sorted(matched_intensity)
    )

    row["matched_comparison"] = ";".join(
        sorted(matched_comparison)
    )

    row["matched_comparison_object"] = ";".join(
        sorted(matched_comparison_objects)
    )

    row["matched_ethnic"] = ";".join(
        sorted(matched_ethnic)
    )

    classified.append(row)


# ---------------------------------------------------------------------------
# Write classified output
# ---------------------------------------------------------------------------

fields = list(classified[0].keys())

classified_path = (
    OUT_DIR / "bodily_whiteness_strict.csv"
)

with classified_path.open(
    "w",
    encoding="utf-8-sig",
    newline="",
) as f:

    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(classified)


# ---------------------------------------------------------------------------
# High-value subset
#
# Score >= 8 means there is at least one reasonably strong signal.
# ---------------------------------------------------------------------------

interesting = [
    row
    for row in classified
    if int(row["strict_score"]) >= 8
]

interesting.sort(
    key=lambda r: (
        -int(r["strict_score"]),
        r["year"][:4] if r["year"][:4].isdigit() else "9999",
    )
)

interesting_path = (
    OUT_DIR / "bodily_whiteness_strict_interesting.csv"
)

with interesting_path.open(
    "w",
    encoding="utf-8-sig",
    newline="",
) as f:

    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(interesting)


# ---------------------------------------------------------------------------
# Albino anchors
# ---------------------------------------------------------------------------

albino = [
    row
    for row in classified
    if "albino" in row["strict_categories"].split(";")
]

albino_path = (
    OUT_DIR / "albino_anchors.csv"
)

with albino_path.open(
    "w",
    encoding="utf-8-sig",
    newline="",
) as f:

    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(albino)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

from collections import Counter

counts = Counter()

for row in classified:
    for category in row["strict_categories"].split(";"):
        counts[category] += 1


print()
print("=" * 72)
print("STRICT CLASSIFICATION COMPLETE")
print("=" * 72)

print()
print(f"Input contexts:          {len(source_rows):,}")
print(f"Classified contexts:     {len(classified):,}")
print(f"Strong candidates >= 8:  {len(interesting):,}")
print(f"Albino anchors:          {len(albino):,}")

print()
print("Categories:")

for category, count in counts.most_common():
    print(f"{category:25} {count:>8,}")

print()
print("Output:")
print(classified_path)
print(interesting_path)
print(albino_path)
