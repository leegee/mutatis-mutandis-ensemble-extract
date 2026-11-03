
from uuid import uuid4

from diachronic_agents.workflows.forward_search import (
    build_forward_search_workflow,
)
from diachronic_agents.retrieval.retrieval_graph import (
    build_retrieval_graph, merge_retrieval_graphs
)

from mutatis_mutandis.lib.corpus_logging import logger


def get_token_span(hit: dict) -> tuple[int, int] | None:
    """Read token offsets using the field names currently supported."""
    field_pairs = (
        ("token_start", "token_end"),
        ("token_start_idx", "token_end_idx"),
        ("token_idx_start", "token_idx_end"),
    )

    for start_key, end_key in field_pairs:
        start = hit.get(start_key)
        end = hit.get(end_key)

        if start is not None and end is not None:
            return int(start), int(end)

    return None


def group_edges_by_seed(edges: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}

    for edge in edges:
        seed_id = edge["source_passage_id"]
        grouped.setdefault(seed_id, []).append(edge)

    return grouped


def log_edge_view(
    label: str,
    edges: list[dict],
    passages_by_id: dict[str, dict],
) -> None:
    grouped = group_edges_by_seed(edges)

    logger.info("")
    logger.info("%s: %d edges", label, len(edges))

    for seed_id, seed_edges in grouped.items():
        logger.info("  Seed %s: %d edges", seed_id[:12], len(seed_edges))

        for edge in sorted(seed_edges, key=lambda e: e.get("rank", 999999)):
            target_id = edge["target_passage_id"]
            passage = passages_by_id.get(target_id, {})

            span = get_token_span(passage)
            span_text = f"{span[0]}:{span[1]}" if span else "NO TOKEN SPAN"

            logger.info(
                "    rank=%s distance=%s year=%s tokens=%s passage=%s",
                edge.get("rank"),
                edge.get("distance"),
                passage.get("pub_year"),
                span_text,
                target_id[:12],
            )


def log_overlap_suppressed(
    suppressed_edges: list[dict],
    passages_by_id: dict[str, dict],
) -> None:
    logger.info("")
    logger.info(
        "OVERLAP-SUPPRESSED EDGES: %d",
        len(suppressed_edges),
    )

    for edge in suppressed_edges:
        target_id = edge["target_passage_id"]
        retained_id = edge.get("retained_target_passage_id")

        passage = passages_by_id.get(target_id, {})
        retained = passages_by_id.get(retained_id, {})

        logger.info(
            "  suppressed=%s retained=%s overlap=%.3f "
            "document=%s year=%s",
            target_id[:12],
            retained_id[:12] if retained_id else None,
            edge.get("overlap_ratio", 0.0),
            passage.get("doc_id"),
            passage.get("pub_year"),
        )

        if not get_token_span(passage):
            logger.warning(
                "    No token span found. Available token fields: %s",
                {
                    key: value
                    for key, value in passage.items()
                    if "token" in key.lower()
                },
            )

        if retained and not get_token_span(retained):
            logger.warning(
                "    Retained passage has no recognised token span: %s",
                {
                    key: value
                    for key, value in retained.items()
                    if "token" in key.lower()
                },
            )


            
workflow = build_forward_search_workflow()

logger.info("LangGraph workflow:")

graph = workflow.get_graph()
for node in graph.nodes:
    logger.info("  node: %s", node)

for edge in graph.edges:
    logger.info("  edge: %s -> %s", edge.source, edge.target)

thread_id = str(uuid4())

result = workflow.invoke(
    {
        "query": "white hair",
        "initial_start_year": 0,
        "initial_end_year": 1500,
        "forward_start_year": 1501,
        "forward_end_year": 1700,
        "representation": "l8",
        "initial_scale": "broad",
        "forward_scale": "broad",
        "initial_limit": 20,
        "seed_limit": 3,
        "transfer_limit": 10,
    },
    config={
        "configurable": {
            "thread_id": thread_id,
        }
    },
)


# ---------------------------------------------------------
# Summary
# ---------------------------------------------------------

logger.info("Forward search completed")
logger.info("Query: %s", result["query"])

logger.info(
    "Initial period: %d–%d",
    *result["initial_period"],
)

logger.info(
    "Forward period: %d–%d",
    *result["forward_period"],
)

logger.info("Representation: %s", result["representation"])
logger.info("Initial scale: %s", result["initial_scale"])
logger.info("Forward scale: %s", result["forward_scale"])

logger.info("Seeds: %d", len(result["seed_ids"]))
logger.info("Unique passages: %d", len(result["passages"]))
logger.info("Retrieval edges: %d", len(result["edges"]))


# ---------------------------------------------------------
# Index passages by ID
# ---------------------------------------------------------

passages_by_id = {
    passage["passage_id"]: passage
    for passage in result["passages"]
}


# ---------------------------------------------------------
# Initial seed details
# ---------------------------------------------------------

logger.info("Initial seeds:")

for index, passage_id in enumerate(result["seed_ids"], start=1):
    passage = passages_by_id[passage_id]

    logger.info("")
    logger.info(
        "SEED %d: %s",
        index,
        passage_id[:12],
    )

    logger.info(
        "  Document: %s",
        passage.get("doc_id"),
    )

    logger.info(
        "  Year: %s | Scale: %s",
        passage.get("pub_year"),
        passage.get("scale"),
    )

    logger.info(
        "  Chars: %s:%s | Words: %s:%s | Tokens: %s:%s",
        passage.get("char_start"),
        passage.get("char_end"),
        passage.get("word_start"),
        passage.get("word_end"),
        passage.get("token_start"),
        passage.get("token_end"),
    )

    logger.info(
        "  %s",
        (passage.get("text") or "").replace("\n", " ")[:400],
    )


# ---------------------------------------------------------
# Group forward retrieval edges by seed
# ---------------------------------------------------------

edges_by_seed: dict[str, list[dict]] = {}

for edge in result["edges"]:
    seed_id = edge["source_passage_id"]

    edges_by_seed.setdefault(seed_id, []).append(edge)


# ---------------------------------------------------------
# Forward results grouped by seed
# ---------------------------------------------------------

logger.info("")
logger.info("=" * 80)
logger.info("FORWARD RETRIEVAL RESULTS BY SEED")
logger.info("=" * 80)

for index, seed_id in enumerate(result["seed_ids"], start=1):
    seed = passages_by_id[seed_id]
    edges = sorted(
        edges_by_seed.get(seed_id, []),
        key=lambda edge: (
            edge["rank"] if edge["rank"] is not None else 999999
        ),
    )

    logger.info("")
    logger.info("-" * 80)
    logger.info(
        "SEED %d: %s | %s | %s",
        index,
        seed_id[:12],
        seed.get("pub_year"),
        seed.get("title") or seed.get("doc_id"),
    )
    logger.info("-" * 80)

    logger.info(
        "Forward matches: %d",
        len(edges),
    )

    for edge in edges:
        target_id = edge["target_passage_id"]
        passage = passages_by_id[target_id]

        distance = edge.get("distance")
        distance_text = (
            f"{distance:.4f}"
            if distance is not None
            else "n/a"
        )

        logger.info("")
        logger.info(
            "  Rank %s | %s | distance=%s",
            edge.get("rank"),
            passage.get("pub_year"),
            distance_text,
        )

        logger.info(
            "  %s",
            passage.get("title") or passage.get("doc_id"),
        )

        logger.info(
            "  %s",
            (passage.get("text") or "").replace("\n", " "),
        )


# Graph
retrieval_graph = build_retrieval_graph(
    result,
    search_direction="forward",
    generation=0,
    search_id=thread_id,
)
logger.info("RETRIEVAL GRAPH")
logger.info("  Nodes: %d", len(retrieval_graph["nodes"]))
logger.info("  Edges: %d", len(retrieval_graph["edges"]))
logger.info("  Searches: %d",     len(retrieval_graph["metadata"].get("search_runs", [])),)
logger.info("  Seeds: %d", len(retrieval_graph["seed_ids"]))
logger.info(
    "  Expanded seeds: %d",
    len(retrieval_graph["expanded_seed_ids"]),
)
logger.info(
    "  Unexpanded seeds: %d",
    len(retrieval_graph["unexpanded_seed_ids"]),
)
logger.info(
    "  Convergences: %d",
    len(retrieval_graph["convergence"]),
)

# Warnings
if result["warnings"]:
    logger.warning("")
    logger.warning("Search warnings:")

    for warning in result["warnings"]:
        logger.warning("  %s", warning)


merged_graph = merge_retrieval_graphs(
    retrieval_graph,
    retrieval_graph,
)

logger.info("GRAPH MERGE TEST")
logger.info("  Nodes: %d", len(merged_graph["nodes"]))
logger.info("  Edges: %d", len(merged_graph["edges"]))
logger.info(
    "  Searches: %d",
    merged_graph["metadata"]["search_count"],
)

# --------------------------------------------------------

logger.info("LLM RESEARCH RECOMMENDATIONS")

from diachronic_agents.llm.groq_client import (
    BODILY_COVERING_CONFIG,
    classify_passages,
)

classification_result = classify_passages(
    passages=retrieval_graph["nodes"],
    config=BODILY_COVERING_CONFIG,
)

logger.info("LLM PASSAGE CLASSIFICATION")

for item in classification_result.classifications:
    logger.info(
        "%-10s | %s | %s | %s",
        item.classification,
        item.feature_type,
        item.passage_id[:12],
        item.reason,
    )
