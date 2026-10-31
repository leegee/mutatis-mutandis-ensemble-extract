from pathlib import Path
import csv
import re

VRT = Path(r"d:/Downloads/clmet3_1/clmet/corpus/clmet.vrt")
OUT = Path(r"d:/Downloads/clmet3_1/clmet/corpus/albino_hits_metadata.csv")

TARGET = re.compile(
    r"^(?:albino|albinos|albinoes|albinism|albinisms|albinotic|albinistic)$",
    re.I,
)

ATTR = re.compile(r'(\w+)="([^"]*)"')

hits = []
meta = {}

with VRT.open(encoding="utf-8") as f:
    for line_no, line in enumerate(f, 1):
        line = line.rstrip("\n")

        if line.startswith("<text "):
            meta = dict(ATTR.findall(line))
            continue

        if line.startswith("<") or not line.strip():
            continue

        parts = line.split("\t")
        if len(parts) < 4:
            continue

        word, pos, lemma, wordclass = parts[:4]

        if TARGET.match(word) or TARGET.match(lemma):
            hits.append({
                "vrt_line": line_no,
                "surface": word,
                "lemma": lemma,
                "pos": pos,
                "wordclass": wordclass,

                "document_id": meta.get("id", ""),
                "file": meta.get("file", ""),
                "period": meta.get("period", ""),
                "quartcent": meta.get("quartcent", ""),
                "decade": meta.get("decade", ""),
                "year": meta.get("year", ""),
                "genre": meta.get("genre", ""),
                "subgenre": meta.get("subgenre", ""),
                "title": meta.get("title", ""),
                "author": meta.get("author", ""),
                "gender": meta.get("gender", ""),
                "author_birth": meta.get("author_birth", ""),
            })

fields = list(hits[0].keys())

with OUT.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(hits)

print(f"HITS: {len(hits)}")
print(f"WROTE: {OUT}")

for h in hits:
    print(
        h["year"],
        h["author"],
        h["title"],
        h["surface"],
        sep=" | "
    )
