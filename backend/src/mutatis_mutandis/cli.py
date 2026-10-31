"""
mutatis_mutandis/cli.py

Command-line front end. Uses the same service layer as the API.

    python src/mutatis_mutandis/cli.py --query "white hair" --limit 30 --scale broad
    python src/mutatis_mutandis/cli.py --vector-id <passage_id> --scale broad
    python src/mutatis_mutandis/cli.py --query "albino" --limit 30 --scale broad --start-year 1971 --end-year 1973
    python src/mutatis_mutandis/cli.py --query "white hair" --representation l8 \
        --limit 50 --scale broad \
        --negative-id <id> --negative-id <id> --beta 0.6

--scale defaults to "local"; the HTTP API searches all scales unless told otherwise.
"""

from __future__ import annotations

import argparse

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, PASSAGE_SCALES
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.macberth import PASSAGE_REPRESENTATIONS

from mutatis_mutandis.service import PassageSearchService, SearchParams
from mutatis_mutandis.years import current_year

logger = get_logger("passage_search.cli")


def parse_args():
    p = argparse.ArgumentParser(description="Search historical passages using MacBERTh embeddings.")
    p.add_argument("--query", help="Text to encode as the search query.")
    p.add_argument("--vector-id", help="Use an existing passage vector (passage_id) as the query.")
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=current_year())
    p.add_argument("--representation", choices=PASSAGE_REPRESENTATIONS, default="l8")
    p.add_argument( "--scale", choices=PASSAGE_SCALES, default="local", help="Passage window scale (default: local).", )
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--negative-id", action="append", default=[], help="Passage ID of a negative example (repeatable).")
    p.add_argument("--beta", type=float, default=0.5, help="Weight of the negative centroid (default 0.5).")
    p.add_argument("--overfetch", type=int, default=5, help="Per-table candidate multiplier when negatives are used (default 5).")
    return p.parse_args()


def log_hit(h: dict):
    logger.info("...............................................................")
    line = (
        f"{h['rank']}. year={h['pub_year']} scale={h.get('scale') or '-'} "
        f"distance={h['distance']:.4f}"
    )
    if h.get("score") is not None:
        line += f" score={h['score']:.4f} sim_neg={h['sim_neg']:.4f}"
    logger.info(line)
    logger.info(f"   corpus={h['corpus']} doc_id={h['doc_id']}")
    logger.info(f"   title={h['title'] or '(untitled)'}")
    logger.info(f"   author={h['author'] or '(unknown)'}")
    logger.info(f"   filepath={h['filepath']}")
    logger.info(
        f"   chars={h.get('char_start')}:{h.get('char_end')} "
        f"words={h['word_start']}:{h['word_end']} "
        f"tokens={h['token_start']}:{h['token_end']}"
    )
    logger.info(f"   passage_id={h['passage_id']}")
    logger.info(f"   {h['text'] or '[Text unavailable]'}")


def main():
    args = parse_args()
    try:
        params = SearchParams(
            query=args.query,
            vector_id=args.vector_id,
            negative_ids=tuple(args.negative_id),
            representation=args.representation,
            scale=args.scale,
            start_year=args.start_year,
            end_year=args.end_year,
            limit=args.limit,
            beta=args.beta,
            overfetch=args.overfetch,
        )
    except ValueError as e:
        raise SystemExit(f"error: {e}")

    service = PassageSearchService(LANCE_INDEXES_DIR, application_name="passage-search-cli")
    try:
        outcome = service.search(params)
    except ValueError as e:  # includes VectorNotFoundError
        raise SystemExit(f"error: {e}")

    for w in outcome.warnings:
        logger.warning(w)
    if not outcome.results:
        logger.info("No results found.")
        return
    for hit in outcome.results:
        log_hit(hit)


if __name__ == "__main__":
    main()
