"""
lib/passage_stem.py - Shared light stemming and vocabulary grouping for passage vocabulary tools.

Used by mask-fillers, phrase mask-fillers, and the substitute-collocate
analysers. Deliberately conservative: a false split is cheap (members are
listed); a false merge hides a word.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from mutatis_mutandis.lib.corpus_logging import logger


# Function words, including Early Modern forms (adapted from word_frequencies.py).
STOP = set("""
a an the and or but nor yet so if unless whether as than at by for from in
into of off on onto out over through to up upon with within without about
above across after against along among around before behind below beneath
beside between beyond down during except inside near outside since toward
towards under underneath until via i me my mine myself we us vs our ours
ourselves you your yours yourself yourselves he him his himself she her hers
herself it its itself they them their theirs themselves this that these those
who whom whose which what whatever whichever when where why how all any
anybody anyone anything both each either everybody everyone everything few
many much neither nobody none no one nothing other others several some
somebody someone something such here there everywhere nowhere somewhere am is
are was were be bee been being have has had having do de doe does did done
doing can cannot could may might must shall should will would ought need dare
not never again already also always ever just merely only quite rather really
very too almost enough especially even still then now once often sometimes
usually because although though while whereas therefore thus hence indeed
perhaps maybe yes thou thee thy thine thyself ye hath hast doth dost art
wilt wouldst shouldst couldst whither whence hither thither hereof thereof
wherein whereof whereby herewith therewith unto amidst amongst betwixt per
mr est ad two three four five six seven eight nine ten haue hee shee wee vpon
vnto vntill whilest yea nay
""".split())


def fold_key(t: str) -> str:
    """Collapse u/v and i/j so 'preuent' and 'prevent' share a key."""
    return t.lower().replace("v", "u").replace("j", "i")


@lru_cache(maxsize=None)
def stem_key(word: str) -> str:
    """
    Light stem for grouping variants of one word.

      preuent/prevent/prevents/preventing/prevented -> one key
      resist/resiste/resisted/resisteth/resists      -> one key
      libertie/liberty/liberties; kingdome/kingdoms; repell/repelled
    """
    w = fold_key(word)

    # plurals, third person, -ie
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("ie") and len(w) > 4:
        w = w[:-2] + "y"
    elif w.endswith("es") and len(w) > 4:
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]

    # verb endings
    for suf, minimum in (("ing", 4), ("eth", 3), ("ed", 3)):
        if w.endswith(suf) and len(w) - len(suf) >= minimum:
            w = w[: -len(suf)]
            break

    # final -e
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]

    # doubled final consonant (repell -> repel)
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
        w = w[:-1]

    return w


@dataclass
class Groups:
    """Vocabulary grouped by light stem for pooled probability mass."""

    group_of: np.ndarray  # vocab id -> group index, -1 if not a candidate
    members: list  # group -> [vocab ids]
    keys: list  # group -> stem key
    index: dict  # stem key -> group
    sel: np.ndarray = field(init=False)
    cache: dict = field(default_factory=dict)  # device -> torch tensors

    def __post_init__(self) -> None:
        self.sel = self.group_of >= 0

    @property
    def n(self) -> int:
        return len(self.members)


def build_groups(tokenizer, vocab_size: int) -> Groups:
    """Whole alphabetic non-stopword vocabulary entries, grouped by stem.

    WordPiece continuation markers ('##') are stripped only for the
    alphabetic / length / stop-word filter; the original token ID is
    retained so probability mass is pooled correctly.
    """
    tokens = tokenizer.convert_ids_to_tokens(
        list(range(min(vocab_size, len(tokenizer))))
    )
    group_of = np.full(vocab_size, -1, dtype=np.int64)
    index: dict[str, int] = {}
    members: list[list[int]] = []
    keys: list[str] = []

    for i, t in enumerate(tokens):
        if t is None:
            continue

        # Normalise only for the eligibility test
        surf = t[2:] if t.startswith("##") else t

        if not surf.isalpha() or len(surf) < 2 or surf.lower() in STOP:
            continue

        k = stem_key(surf)          # stem the cleaned surface form
        if k not in index:
            index[k] = len(members)
            members.append([])
            keys.append(k)
        group_of[i] = index[k]
        members[index[k]].append(i)

    return Groups(group_of, members, keys, index)


def content_word(w: str, excl_keys: set[str]) -> bool:
    """True if *w* is a non-stop, alphabetic content word outside *excl_keys*."""
    lw = w.lower()
    return (
        lw.isalpha()
        and len(lw) > 1
        and lw not in STOP
        and stem_key(lw) not in excl_keys
    )


def span_of(passage: dict, w_idx: int) -> tuple[int, int]:
    """
    (start, end) word positions masked for an occurrence.

    Seed phrases carry a ``span``; any other position (baseline words,
    single-word seeds) is one word.
    """
    s, e = passage.get("span", (w_idx, w_idx))
    return (s, e) if w_idx == s else (w_idx, w_idx)