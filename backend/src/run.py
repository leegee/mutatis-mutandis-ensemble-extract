
from uuid import uuid4

from diachronic_agents.workflows.reverse_search import (
    build_reverse_search_workflow,
)

from mutatis_mutandis.lib.corpus_logging import logger


workflow = build_reverse_search_workflow()

result = workflow.invoke(
    {
        "query": "white hair",
        "initial_start_year": 1950,
        "initial_end_year": 2000,
        "historical_start_year": 1900,
        "historical_end_year": 1949,
        "representation": "l8",
        "initial_scale": "broad",
        "historical_scale": "broad",
        "initial_limit": 20,
        "seed_limit": 3,
        "transfer_limit": 10,
    },
    config={
        "configurable": {
            "thread_id": str(uuid4()),
        }
    },
)

logger.info("Reverse search completed")
logger.info("Query: %s", result["query"])
logger.info(
    "Initial period: %d–%d",
    *result["initial_period"],
)
logger.info(
    "Historical period: %d–%d",
    *result["historical_period"],
)
logger.info("Representation: %s", result["representation"])
logger.info("Initial scale: %s", result["initial_scale"])
logger.info("Historical scale: %s", result["historical_scale"])

logger.info("Seeds: %d", len(result["seed_ids"]))
logger.info("Unique passages: %d", len(result["passages"]))
logger.info("Retrieval edges: %d", len(result["edges"]))

logger.info("Seed passage IDs:")

passages_by_id = {
    p["passage_id"]: p
    for p in result["passages"]
}

logger.info("Seed passage IDs:")
for passage_id in result["seed_ids"]:
    logger.info("  %s", passage_id)

logger.info("Initial seed details:")

for passage_id in result["seed_ids"]:
    p = passages_by_id[passage_id]

    logger.info(
        "  %s | %s | year=%s | scale=%s",
        passage_id[:12],
        p.get("doc_id"),
        p.get("pub_year"),
        p.get("scale"),
    )

    logger.info(
        "    chars=%s:%s | words=%s:%s | tokens=%s:%s",
        p.get("char_start"),
        p.get("char_end"),
        p.get("word_start"),
        p.get("word_end"),
        p.get("token_start"),
        p.get("token_end"),
    )

    logger.info(
        "    %s",
        (p.get("text") or "").replace("\n", " ")[:400],
    )

logger.info("Historical retrieval edges:")

for edge in result["edges"]:
    logger.info(
        "  %s -> %s | year=%s | rank=%s | cosine_distance=%s",
        edge["source_passage_id"][:12],
        edge["target_passage_id"][:12],
        edge["target_pub_year"],
        edge["rank"],
        (
            f"{edge['distance']:.4f}"
            if edge["distance"] is not None
            else "n/a"
        ),
    )

logger.info("Historical passages:")

seen = set()

for edge in result["edges"]:
    passage_id = edge["target_passage_id"]

    if passage_id in seen:
        continue

    seen.add(passage_id)
    passage = passages_by_id[passage_id]

    logger.info(
        "%s | %s | %s | distance=%.4f",
        passage_id[:12],
        passage.get("pub_year"),
        passage.get("title"),
        edge["distance"],
    )

    logger.info(
        "%s",
        (passage.get("text") or "").replace("\n", " "),
    )
    logger.info("")

if result["warnings"]:
    logger.warning("Search warnings:")
    for warning in result["warnings"]:
        logger.warning("  %s", warning)
        