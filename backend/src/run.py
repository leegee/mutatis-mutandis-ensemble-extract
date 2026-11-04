
from uuid import uuid4

from diachronic_agents.workflows.forward_search import (
    build_forward_search_workflow,
)
from diachronic_agents.retrieval.retrieval_graph import (
    build_retrieval_graph,
    merge_retrieval_graphs,
)
from diachronic_agents.llm.passage_classifier import classify_passages
from diachronic_agents.retrieval.prospect_selector import (
    select_prospects,
    rank_prospects_by_convergence,
)
from diachronic_agents.visualization.graph_visualizer import (
    visualise_retrieval_graph,
    report_isolated_nodes,
)
from diachronic_agents.classification_configs import ALBINISM_CONFIG
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR


logger = get_logger(__name__)

REPRESENTATION = "l8"
SCALE = "broad"
INITIAL_QUERY = "white hair"  # or "albino"

INITIAL_PERIOD = (0, 1500)
FORWARD_PERIODS = {
    0: (1501, 1700),
    1: (1701, 1800),
    2: (1801, 1900),
    3: (1901, 2000),
}

INITIAL_LIMIT = 20
SEED_LIMIT = 3
TRANSFER_LIMIT = 10
EXPANSION_SEED_COUNT = 3
PROSPECT_LIMIT = 10


def classify_and_select_prospects(
    passages: list[dict],
    retrieval_graph: dict,
    per_feature_limit: int = PROSPECT_LIMIT,
) -> tuple[object, list[dict]]:
    """Classify passages, select relevant features, and rank by convergence."""

    classification_result = classify_passages(
        passages=passages,
        config=ALBINISM_CONFIG,
    )

    prospects = select_prospects(
        passages=passages,
        classification_result=classification_result,
        feature_types={"human_hair", "complexion"},
        per_feature_limit=per_feature_limit,
    )

    prospects = rank_prospects_by_convergence(
        prospects=prospects,
        retrieval_graph=retrieval_graph,
    )

    return classification_result, prospects


def log_prospects(title: str, prospects: list[dict]) -> None:
    logger.info(title)

    for index, prospect in enumerate(prospects, start=1):
        logger.info(
            "%02d | %s | %s | year=%s | feature=%s | "
            "sources=%s | edges=%s | %s",
            index,
            prospect.get("passage_id"),
            prospect.get("classification"),
            prospect.get("pub_year"),
            prospect.get("feature_type"),
            prospect.get("incoming_source_count", 0),
            prospect.get("incoming_edge_count", 0),
            prospect.get("reason", ""),
        )


def attach_classifications(
    retrieval_graph: dict,
    classification_results: list,
) -> dict:
    """Attach passage classifications to corresponding graph nodes."""

    classifications_by_id = {}

    for result in classification_results:
        if result is None:
            continue

        for item in result.classifications:
            if isinstance(item, dict):
                passage_id = item["passage_id"]
                classification = item.get("classification")
                feature_type = item.get("feature_type")
                reason = item.get("reason")
            else:
                passage_id = item.passage_id
                classification = item.classification
                feature_type = item.feature_type
                reason = item.reason

            classifications_by_id[passage_id] = {
                "classification": classification,
                "feature_type": feature_type,
                "classification_reason": reason,
            }

    for node in retrieval_graph["nodes"]:
        passage_id = node.get("passage_id", node["id"])
        classification = classifications_by_id.get(passage_id)

        if classification:
            node.update(classification)

    return retrieval_graph


def log_cumulative_report(
    graph: dict,
    classification_results: list,
) -> None:
    """Log a chronological report of the complete retrieval graph."""

    classifications_by_id = {}

    for result in classification_results:
        if result is None:
            continue

        for item in result.classifications:
            classifications_by_id.setdefault(
                item.passage_id,
                {
                    "classification": item.classification,
                    "feature_type": item.feature_type,
                    "reason": item.reason,
                },
            )

    incoming_counts = {}
    outgoing_counts = {}

    for edge in graph["edges"]:
        incoming_counts[edge["target"]] = (
            incoming_counts.get(edge["target"], 0) + 1
        )
        outgoing_counts[edge["source"]] = (
            outgoing_counts.get(edge["source"], 0) + 1
        )

    nodes = sorted(
        graph["nodes"],
        key=lambda node: (
            node.get("pub_year") or 0,
            node.get("title") or "",
            node["id"],
        ),
    )

    logger.info("=" * 100)
    logger.info("CUMULATIVE CHRONOLOGICAL PASSAGE REPORT")
    logger.info("=" * 100)

    for node in nodes:
        passage_id = node.get("passage_id", node["id"])
        classification = classifications_by_id.get(passage_id, {})

        logger.info(
            "%4s | GEN %s | %-12s | %-12s | IN=%2d | OUT=%2d | %s",
            node.get("pub_year", "?"),
            node.get("generation", "?"),
            classification.get("classification", "unclassified"),
            classification.get("feature_type", "unknown"),
            incoming_counts.get(node["id"], 0),
            outgoing_counts.get(node["id"], 0),
            node.get("title", "Untitled"),
        )

        if classification.get("reason"):
            logger.info("       REASON: %s", classification["reason"])

    logger.info("=" * 100)
    logger.info("CUMULATIVE EDGE REPORT")
    logger.info("=" * 100)

    for generation in sorted({
        edge.get("generation", 0)
        for edge in graph["edges"]
    }):
        generation_edges = [
            edge for edge in graph["edges"]
            if edge.get("generation", 0) == generation
        ]

        logger.info(
            "GENERATION %s: %d retrieval edges",
            generation,
            len(generation_edges),
        )

    logger.info("=" * 100)
    logger.info("CONVERGENCE REPORT")
    logger.info("=" * 100)

    nodes_by_id = {node["id"]: node for node in nodes}

    for item in graph["convergence"]:
        target = nodes_by_id.get(item["target_passage_id"])

        if target is None:
            continue

        logger.info(
            "CONVERGENCE | %s | %s | %d incoming sources",
            target.get("pub_year", "?"),
            target.get("title", "Untitled"),
            item["source_count"],
        )

    logger.info("=" * 100)


def run_generation(
    workflow,
    generation: int,
    *,
    seed_passages: list[dict] | None = None,
    query: str | None = None,
) -> tuple[dict, dict, object, list[dict]]:
    """Run one retrieval generation and its classification stage."""

    start_year, end_year = FORWARD_PERIODS[generation]
    thread_id = str(uuid4())

    logger.info("=" * 72)
    logger.info("GENERATION %d: FORWARD SEARCH (%d–%d)", generation, start_year, end_year)
    logger.info("=" * 72)

    inputs = {
        "representation": REPRESENTATION,
        "forward_scale": SCALE,
        "transfer_limit": TRANSFER_LIMIT,
        "forward_start_year": start_year,
        "forward_end_year": end_year,
    }

    if seed_passages is not None:
        inputs["seed_passages"] = seed_passages
    else:
        inputs.update({
            "query": query,
            "initial_start_year": INITIAL_PERIOD[0],
            "initial_end_year": INITIAL_PERIOD[1],
            "initial_scale": SCALE,
            "initial_limit": INITIAL_LIMIT,
            "seed_limit": SEED_LIMIT,
        })

    result = workflow.invoke(
        inputs,
        config={"configurable": {"thread_id": thread_id}},
    )

    logger.info(
        "Generation %d: %d passages, %d edges",
        generation,
        len(result["passages"]),
        len(result["edges"]),
    )

    graph = build_retrieval_graph(
        result=result,
        search_direction="forward",
        generation=generation,
        search_id=thread_id,
    )

    logger.info(
        "Generation %d graph: %d nodes, %d edges",
        generation,
        len(graph["nodes"]),
        len(graph["edges"]),
    )

    classification, prospects = classify_and_select_prospects(
        passages=graph["nodes"],
        retrieval_graph=graph,
    )

    log_prospects(f"GENERATION {generation} PROSPECTS", prospects)

    return result, graph, classification, prospects


def select_expansion_seeds(
    prospects: list[dict],
    passages: list[dict],
    count: int = EXPANSION_SEED_COUNT,
) -> list[dict]:
    """Select passages from a generation's results for the next expansion."""

    passages_by_id = {
        passage["passage_id"]: passage
        for passage in passages
    }

    seeds = []

    for prospect in prospects[:count]:
        passage_id = prospect["passage_id"]
        passage = passages_by_id.get(passage_id)

        if passage is None:
            logger.warning(
                "Cannot expand prospect %s: passage not found",
                passage_id,
            )
            continue

        seeds.append(passage)

    logger.info("Expansion seeds: %d", len(seeds))

    for seed in seeds:
        logger.info(
            "EXPANSION SEED | year=%s | %s | %s",
            seed.get("pub_year"),
            seed.get("title"),
            seed.get("passage_id"),
        )

    return seeds


def merge_all_graphs(graphs: dict[int, dict]) -> dict:
    """Merge all generation graphs into one cumulative graph."""

    cumulative_graph = None

    for generation in sorted(graphs):
        graph = graphs[generation]

        if cumulative_graph is None:
            cumulative_graph = graph
        else:
            cumulative_graph = merge_retrieval_graphs(
                cumulative_graph,
                graph,
            )

    return cumulative_graph


def main() -> None:
    workflow = build_forward_search_workflow()

    # Results are retained by generation number.
    results = {}
    graphs = {}
    classifications = {}
    prospects = {}

    # ---------------------------------------------------------
    # GENERATION 0: Initial query and first forward retrieval
    # ---------------------------------------------------------

    (
        results[0],
        graphs[0],
        classifications[0],
        prospects[0],
    ) = run_generation(
        workflow,
        generation=0,
        query=INITIAL_QUERY,
    )

    # ---------------------------------------------------------
    # GENERATIONS 1–3: Forward expansion
    # ---------------------------------------------------------

    for generation in range(1, max(FORWARD_PERIODS) + 1):
        seed_passages = select_expansion_seeds(
            prospects=prospects[generation - 1],
            passages=results[generation - 1]["passages"],
        )

        if not seed_passages:
            logger.warning(
                "No expansion seeds for Generation %d; stopping.",
                generation,
            )
            break

        (
            results[generation],
            graphs[generation],
            classifications[generation],
            prospects[generation],
        ) = run_generation(
            workflow,
            generation=generation,
            seed_passages=seed_passages,
        )

    # ---------------------------------------------------------
    # MERGE ALL GENERATIONS
    # ---------------------------------------------------------

    cumulative_graph = merge_all_graphs(graphs)

    # ---------------------------------------------------------
    # CUMULATIVE CLASSIFICATION DATA
    # ---------------------------------------------------------

    attach_classifications(
        retrieval_graph=cumulative_graph,
        classification_results=list(classifications.values()),
    )

    # ---------------------------------------------------------
    # CUMULATIVE REPORT
    # ---------------------------------------------------------

    log_cumulative_report(
        graph=cumulative_graph,
        classification_results=list(classifications.values()),
    )

    # ---------------------------------------------------------
    # COMPLETE GRAPH DIAGNOSTICS
    # ---------------------------------------------------------

    incoming_counts = {}
    outgoing_counts = {}

    for edge in cumulative_graph["edges"]:
        incoming_counts[edge["target"]] = (
            incoming_counts.get(edge["target"], 0) + 1
        )
        outgoing_counts[edge["source"]] = (
            outgoing_counts.get(edge["source"], 0) + 1
        )

    logger.info("=" * 72)
    logger.info("COMPLETE CUMULATIVE RETRIEVAL GRAPH")
    logger.info("=" * 72)
    logger.info("Total nodes: %d", len(cumulative_graph["nodes"]))
    logger.info("Total edges: %d", len(cumulative_graph["edges"]))
    logger.info("Searches: %d", cumulative_graph["metadata"]["search_count"])
    logger.info("Convergence points: %d", len(cumulative_graph["convergence"]))

    logger.info("-" * 72)
    logger.info("NODE CONNECTIVITY")
    logger.info("-" * 72)

    for node in sorted(
        cumulative_graph["nodes"],
        key=lambda n: (
            n.get("pub_year") or 0,
            n.get("title") or "",
        ),
    ):
        logger.info(
            "NODE | year=%s | gen=%s | in=%d | out=%d | "
            "feature=%s | %s",
            node.get("pub_year", "?"),
            node.get("generation", "?"),
            incoming_counts.get(node["id"], 0),
            outgoing_counts.get(node["id"], 0),
            node.get("feature_type", "unclassified"),
            node.get("title", "Untitled"),
        )

    report_isolated_nodes(cumulative_graph)

    # ---------------------------------------------------------
    # FULL GRAPH VISUALISATION
    # ---------------------------------------------------------

    graph_dir = OUT_DIR / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)

    graph_path = visualise_retrieval_graph(
        cumulative_graph,
        output_path=graph_dir / "retrieval_graph_all_generations.html",
    )

    logger.info("=" * 72)
    logger.info("VISUALISATION COMPLETE")
    logger.info("=" * 72)
    logger.info("Complete graph: %s", graph_path)


if __name__ == "__main__":
    main()
