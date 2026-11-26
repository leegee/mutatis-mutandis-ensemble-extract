"""
ingest.lib.whiteness_filter.py

Shared vocabulary-based whiteness screening functions.

Keep the vocabulary in ``wordlist_whiteness.py``. Both corpus ingestion and
standalone screening should call these functions so their decisions agree.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import logging

from mutatis_mutandis.ingest.lib.wordlist_whiteness import (
    WHITENESS,
    WHITENESS_WEIGHTS,
    WEAK_WHITENESS_PATTERNS,
)

logger = logging.getLogger(__name__)

MIN_WHITENESS_SCORE = 2.0

WINDOW_WORDS = 100
WINDOW_LEFT = WINDOW_WORDS // 2
WINDOW_RIGHT = WINDOW_WORDS - WINDOW_LEFT - 1


def whiteness_seed_score(tokens: Sequence[str]) -> tuple[float, Counter[str]]:
    """Return the weighted vocabulary score and counts of matched terms."""
    hits = Counter(
        token.lower()
        for token in tokens
        if token.lower() in WHITENESS
    )
    score = sum(
        count * WHITENESS_WEIGHTS.get(lemma, 1.0)
        for lemma, count in hits.items()
    )
    return float(score), hits


def whiteness_filter_reason(tokens: Sequence[str]) -> tuple[bool, str, float, Counter[str]]:
    """Return pass/fail, reason, score and hits using the ingestion rules."""
    score, hits = whiteness_seed_score(tokens)

    if not hits:
        return False, "no_whiteness_terms", score, hits

    seeds = set(hits)
    if any(seeds <= weak for weak in WEAK_WHITENESS_PATTERNS):
        return False, "weak_terms_only", score, hits

    if score < MIN_WHITENESS_SCORE:
        return False, "below_minimum_score", score, hits

    return True, "passed", score, hits


def passes_whiteness_filter(doc_id: str, tokens: Sequence[str]) -> bool:
    """Compatibility wrapper for the ingestion pipeline's existing API."""
    passed, _, score, hits = whiteness_filter_reason(tokens)
    if passed:
        logger.info("Whiteness filter PASS: %s score=%s hits=%s", doc_id, score, dict(hits))
    return passed


def extract_sparse_windows(
    tokens: Sequence[str],
    left: int = WINDOW_LEFT,
    right: int = WINDOW_RIGHT,
) -> list[tuple[int, str]]:
    """Return original token positions within windows around all seed terms."""
    if not tokens:
        return []

    hits = [i for i, token in enumerate(tokens) if token.lower() in WHITENESS]
    if not hits:
        return []

    included: set[int] = set()
    for hit in hits:
        included.update(range(max(0, hit - left), min(len(tokens), hit + right + 1)))

    return [(i, tokens[i]) for i in sorted(included)]
