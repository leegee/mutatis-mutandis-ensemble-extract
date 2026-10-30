
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re


from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_config import OUT_DIR


OUTPUT = OUT_DIR / Path("eebo_word_frequencies.csv")
TOP_N = 500

# Modern and Early Modern English grammatical words.
STOPWORDS = set("""
a an the
and or but nor yet so
if unless whether
as than
at by for from in into of off on onto out over
through to up upon with within without
about above across after against along among around before
behind below beneath beside between beyond down during
except inside near outside since toward towards under underneath
until via
i me my mine myself
we us vs our ours ourselves
you your yours yourself yourselves
he him his himself
she her hers herself
it its itself
they them their theirs themselves
this that these those
who whom whose which what whatever whichever
when where why how
all any anybody anyone anything
both each either everybody everyone everything
few many much neither nobody none no one nothing
other others several some somebody someone something
such
here there everywhere nowhere somewhere
am is are was were be bee been being
have has had having
do de doe does did done doing
can cannot could may might must shall should will would
ought need dare
not never
again already also always ever
just merely only quite rather really very
too almost enough especially even still
then now once often sometimes usually
because although though while whereas
therefore thus hence
indeed perhaps maybe
yes no
than
thou thee thy thine thyself
ye you
hath hast doth dost
art wert wast were't
wilt wouldst shouldst couldst mightst
shalt shalt
whither whence hither thither
hereof thereof wherein whereof
whereby herewith therewith
unto amidst amongst betwixt
per mr est ad
one two three four five six seven eight nine ten
""".split())

# Include common contractions and spelling variants where useful.
STOPWORDS.update({
    "haue", "hath", "hast", "hee", "shee", "thee",
    "thou", "thy", "thine", "hee's", "yea", "nay",
    "wee", "wee'l", "you'l", "they'l",
    "vpon", "vnto", "vntill", "amongst", "whilest",
})

# Keep tokens containing letters; discard punctuation/numeric-only tokens.
WORD_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def keep_token(token):
    if not token:
        return False

    token_lower = token.casefold()

    if not WORD_RE.search(token):
        return False

    if token_lower in STOPWORDS:
        return False

    # Exclude one-character remnants, but retain "I" if desired
    # by removing this condition.
    if len(token_lower) < 2:
        return False

    return True


def main():
    frequencies = Counter()
    pamphlets = defaultdict(set)

    with get_connection() as conn:
        with conn.cursor(name="eebo_token_stream") as cur:
            cur.execute("""
                SELECT token, doc_id
                FROM pamphlet_tokens
                WHERE token IS NOT NULL
                  AND token <> ''
            """)

            while True:
                rows = cur.fetchmany(100_000)
                if not rows:
                    break

                for token, doc_id in rows:
                    if keep_token(token):
                        # Preserve the original surface form and casing.
                        frequencies[token] += 1
                        pamphlets[token].add(doc_id)

    ranked = sorted(
        frequencies.items(),
        key=lambda item: (-item[1], item[0].casefold(), item[0])
    )[:TOP_N]

    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "surface_form", "frequency", "pamphlet_count"
        ])

        for rank, (word, count) in enumerate(ranked, start=1):
            writer.writerow([
                rank, word, count, len(pamphlets[word])
            ])

    print(f"Distinct retained forms: {len(frequencies):,}")
    print(f"Results written to: {OUTPUT.resolve()}")
    print(f"\nTop {min(TOP_N, len(ranked))} words:")

    for rank, (word, count) in enumerate(ranked[:1000], start=1):
        print(
            f"{rank:>3}. {word:<24} "
            f"{count:>9,} occurrences  "
            f"{len(pamphlets[word]):>6,} pamphlets"
        )


if __name__ == "__main__":
    main()
