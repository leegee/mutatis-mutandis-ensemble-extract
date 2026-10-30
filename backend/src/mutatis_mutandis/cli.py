"""
mutatis_mutandis/cli.py

Command-line front end. Uses the same service layer as the API.

    python src/mutatis_mutandis/cli.py --query "white hair" --limit 30 --scale broad 
    python src/mutatis_mutandis/cli.py --vector-id <passage_id>
    python src/mutatis_mutandis/cli.py --query "white hair" \
        --negative-id <id> --negative-id <id> --beta 0.6 --scale broad 


    python src/mutatis_mutandis/cli.py --query "white hair" --limit 30 --scale broad 

    python src/mutatis_mutandis/cli.py \
        --vector-id ef2f4aaf68dc6c924a2f1218e470a555060be2cb886a0ef1ebf169b800508f8a \
        --limit 30
        --scale broad 

    python src/mutatis_mutandis/cli.py \
        --query "white hair" --representation l8 --limit 50 \
        --scale broad \
        --negative-id dfbee39870fbbababa5fc24da247fb8468a82350bca1170209458b84568be2c3 \
        --negative-id afee38e3452766ffd28bc725ba733cec845fe8cb338c8ef93a52f850223fdbe7 \
        --negative-id b18fa10570b4402f240375c0f45fe9d179493486ab8abe32f285f112b7ff8126 \
        --beta 0.6

"""

from __future__ import annotations

import argparse

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, PASSAGE_SCALES
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.macberth import PASSAGE_REPRESENTATIONS

from mutatis_mutandis.service import PassageSearchService, SearchParams

logger = get_logger("passage_search.cli")


def parse_args():
    p = argparse.ArgumentParser(description="Search historical passages using MacBERTh embeddings.")
    p.add_argument("--query", help="Text to encode as the search query.")
    p.add_argument("--vector-id", help="Use an existing passage vector (passage_id) as the query.")
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=2030)
    p.add_argument("--representation", choices=PASSAGE_REPRESENTATIONS, default="l8")
    p.add_argument( "--scale", choices=PASSAGE_SCALES, default="local", help="Passage window scale (default: local).", )
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--negative-id", action="append", default=[], help="Passage ID of a negative example (repeatable).")
    p.add_argument("--beta", type=float, default=0.5, help="Weight of the negative centroid (default 0.5).")
    p.add_argument("--overfetch", type=int, default=5, help="Per-table candidate multiplier when negatives are used (default 5).")
    return p.parse_args()


def log_hit(h: dict):
    logger.info("...............................................................")
    line = f"{h['rank']}. year={h['pub_year']} distance={h['distance']:.4f}"
    if h.get("score") is not None:
        line += f" score={h['score']:.4f} sim_neg={h['sim_neg']:.4f}"
    logger.info(line)
    logger.info(f"   corpus={h['corpus']} doc_id={h['doc_id']}")
    logger.info(f"   title={h['title'] or '(untitled)'}")
    logger.info(f"   author={h['author'] or '(unknown)'}")
    logger.info(f"   filepath={h['filepath']}")
    logger.info(f"   words={h['word_start']}:{h['word_end']} tokens={h['token_start']}:{h['token_end']}")
    logger.info(f"   passage_id={h['passage_id']}")
    logger.info(f"   {h['text'] or '[Text unavailable]'}")
    logger.info(
        f"   scale={h.get('scale')} words={h['word_start']}:{h['word_end']} "
        f"   tokens={h['token_start']}:{h['token_end']}"
    )


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
    outcome = service.search(params)

    for w in outcome.warnings:
        logger.warning(w)
    if not outcome.results:
        logger.info("No results found.")
        return
    for hit in outcome.results:
        log_hit(hit)


if __name__ == "__main__":
    main()
