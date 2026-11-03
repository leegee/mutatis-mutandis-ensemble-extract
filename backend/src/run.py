
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


def classify_and_select_prospects(
    passages: list[dict],
    retrieval_graph: dict,
    per_feature_limit: int = 10,
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


def attach_classifications(retrieval_graph, classification_results):
    """Attach passage classifications to the corresponding graph nodes."""

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
            logger.info(
                "       REASON: %s",
                classification["reason"],
            )

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

    for item in graph["convergence"]:
        target_id = item["target_passage_id"]

        target = next(
            (node for node in nodes if node["id"] == target_id),
            None,
        )

        if target is None:
            continue

        logger.info(
            "CONVERGENCE | %s | %s | %d incoming sources",
            target.get("pub_year", "?"),
            target.get("title", "Untitled"),
            item["source_count"],
        )

    logger.info("=" * 100)
    

def main() -> None:
    generation_2_result = None
    generation_3_result = None

    retrieval_graph_2 = None
    retrieval_graph_3 = None

    classification_2 = None
    classification_3 = None

    prospects_2 = []
    prospects_3 = []

    workflow = build_forward_search_workflow()

    # ---------------------------------------------------------
    # GENERATION 0: Initial lexical search and forward retrieval
    # ---------------------------------------------------------

    thread_id = str(uuid4())

    logger.info("=" * 72)
    logger.info("GENERATION 0: INITIAL SEARCH")
    logger.info("=" * 72)

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

    passages_by_id = {
        passage["passage_id"]: passage
        for passage in result["passages"]
    }

    logger.info(
        "Initial results: %d",
        len(result["initial_results"]),
    )
    logger.info(
        "Selected seeds: %d",
        len(result["seed_ids"]),
    )
    logger.info(
        "Forward passages: %d",
        len(result["forward_results"]),
    )
    logger.info(
        "Forward edges: %d",
        len(result["edges"]),
    )

    for seed_id in result["seed_ids"]:
        seed = passages_by_id.get(seed_id)
        if seed:
            logger.info(
                "SEED | year=%s | %s | %s",
                seed.get("pub_year"),
                seed.get("title"),
                seed_id,
            )

    retrieval_graph_0 = build_retrieval_graph(
        result=result,
        search_direction="forward",
        generation=0,
        search_id=thread_id,
    )

    logger.info(
        "Generation 0 graph: %d nodes, %d edges",
        len(retrieval_graph_0["nodes"]),
        len(retrieval_graph_0["edges"]),
    )

    # ---------------------------------------------------------
    # GENERATION 0: Classification and prospect selection
    # ---------------------------------------------------------

    logger.info("=" * 72)
    logger.info("GENERATION 0: CLASSIFICATION AND PROSPECT SELECTION")
    logger.info("=" * 72)

    classification_0, prospects_0 = classify_and_select_prospects(
        passages=retrieval_graph_0["nodes"],
        retrieval_graph=retrieval_graph_0,
        per_feature_limit=10,
    )

    log_prospects(
        "GENERATION 0 PROSPECTS",
        prospects_0,
    )

    # ---------------------------------------------------------
    # Select expansion seeds
    # ---------------------------------------------------------

    expansion_seed_count = 3

    expansion_prospects = prospects_0[:expansion_seed_count]

    expansion_seeds = []

    for prospect in expansion_prospects:
        passage_id = prospect["passage_id"]
        passage = passages_by_id.get(passage_id)

        if passage is None:
            logger.warning(
                "Cannot expand prospect %s: passage not found",
                passage_id,
            )
            continue

        expansion_seeds.append(passage)

    logger.info("=" * 72)
    logger.info("GENERATION 1 EXPANSION SEEDS")
    logger.info("=" * 72)

    for seed in expansion_seeds:
        logger.info(
            "EXPANSION SEED | year=%s | %s | %s",
            seed.get("pub_year"),
            seed.get("title"),
            seed.get("passage_id"),
        )

    if not expansion_seeds:
        logger.warning("No expansion seeds selected; stopping.")
        return

    # ---------------------------------------------------------
    # GENERATION 1: Forward search from selected prospects
    # ---------------------------------------------------------

    generation_1_thread_id = str(uuid4())

    logger.info("=" * 72)
    logger.info("GENERATION 1: FORWARD EXPANSION")
    logger.info("=" * 72)

    generation_1_result = workflow.invoke(
        {
            "seed_passages": expansion_seeds,
            "forward_start_year": 1701,
            "forward_end_year": 1800,
            "representation": "l8",
            "forward_scale": "broad",
            "transfer_limit": 10,
        },
        config={
            "configurable": {
                "thread_id": generation_1_thread_id,
            }
        },
    )

    logger.info(
        "Generation 1 passages: %d",
        len(generation_1_result["passages"]),
    )
    logger.info(
        "Generation 1 edges: %d",
        len(generation_1_result["edges"]),
    )

    retrieval_graph_1 = build_retrieval_graph(
        result=generation_1_result,
        search_direction="forward",
        generation=1,
        search_id=generation_1_thread_id,
    )

    logger.info(
        "Generation 1 graph: %d nodes, %d edges",
        len(retrieval_graph_1["nodes"]),
        len(retrieval_graph_1["edges"]),
    )

    # ---------------------------------------------------------
    # GENERATION 1: Classification and prospect selection
    # ---------------------------------------------------------

    logger.info("=" * 72)
    logger.info("GENERATION 1: CLASSIFICATION AND PROSPECT SELECTION")
    logger.info("=" * 72)

    classification_1, prospects_1 = classify_and_select_prospects(
        passages=retrieval_graph_1["nodes"],
        retrieval_graph=retrieval_graph_1,
        per_feature_limit=10,
    )

    log_prospects(
        "GENERATION 1 PROSPECTS",
        prospects_1,
    )



    # ---------------------------------------------------------
    # GENERATION 2: Forward expansion, 1801–1900
    # ---------------------------------------------------------

    generation_2_seed_count = 3
    generation_2_prospects = prospects_1[:generation_2_seed_count]

    generation_2_seeds = []

    # Include only passages actually discovered in Generation 1.
    generation_1_passages_by_id = {
        passage["passage_id"]: passage
        for passage in generation_1_result["passages"]
    }

    for prospect in generation_2_prospects:
        passage_id = prospect["passage_id"]
        passage = generation_1_passages_by_id.get(passage_id)

        if passage is None:
            logger.warning(
                "Cannot expand Generation 1 prospect %s: passage not found",
                passage_id,
            )
            continue

        generation_2_seeds.append(passage)

    logger.info("=" * 72)
    logger.info("GENERATION 2 EXPANSION SEEDS")
    logger.info("=" * 72)

    for seed in generation_2_seeds:
        logger.info(
            "EXPANSION SEED | year=%s | %s | %s",
            seed.get("pub_year"),
            seed.get("title"),
            seed.get("passage_id"),
        )

    if not generation_2_seeds:
        logger.warning("No Generation 2 seeds selected; skipping.")
    else:
        generation_2_thread_id = str(uuid4())

        logger.info("=" * 72)
        logger.info("GENERATION 2: FORWARD EXPANSION (1801–1900)")
        logger.info("=" * 72)

        generation_2_result = workflow.invoke(
            {
                "seed_passages": generation_2_seeds,
                "forward_start_year": 1801,
                "forward_end_year": 1900,
                "representation": "l8",
                "forward_scale": "broad",
                "transfer_limit": 10,
            },
            config={
                "configurable": {
                    "thread_id": generation_2_thread_id,
                }
            },
        )

        logger.info(
            "Generation 2 passages: %d",
            len(generation_2_result["passages"]),
        )
        logger.info(
            "Generation 2 edges: %d",
            len(generation_2_result["edges"]),
        )

        retrieval_graph_2 = build_retrieval_graph(
            result=generation_2_result,
            search_direction="forward",
            generation=2,
            search_id=generation_2_thread_id,
        )

        logger.info(
            "Generation 2 graph: %d nodes, %d edges",
            len(retrieval_graph_2["nodes"]),
            len(retrieval_graph_2["edges"]),
        )

        # Classify and rank Generation 2 discoveries.
        classification_2, prospects_2 = classify_and_select_prospects(
            passages=retrieval_graph_2["nodes"],
            retrieval_graph=retrieval_graph_2,
            per_feature_limit=10,
        )

        log_prospects(
            "GENERATION 2 PROSPECTS",
            prospects_2,
        )

    if generation_2_result is None:
        logger.warning(
            "Generation 2 did not run; cannot perform Generation 3."
        )
        return

    # ---------------------------------------------------------
    # GENERATION 3: Forward expansion, 1901–2000
    # ---------------------------------------------------------

    generation_3_seed_count = 3
    generation_3_prospects = prospects_2[:generation_3_seed_count]

    generation_3_passages_by_id = {
        passage["passage_id"]: passage
        for passage in generation_2_result["passages"]
    }

    generation_3_seeds = []

    for prospect in generation_3_prospects:
        passage_id = prospect["passage_id"]
        passage = generation_3_passages_by_id.get(passage_id)

        if passage is None:
            logger.warning(
                "Cannot expand Generation 2 prospect %s: passage not found",
                passage_id,
            )
            continue

        generation_3_seeds.append(passage)

    logger.info("=" * 72)
    logger.info("GENERATION 3 EXPANSION SEEDS")
    logger.info("=" * 72)

    for seed in generation_3_seeds:
        logger.info(
            "EXPANSION SEED | year=%s | %s | %s",
            seed.get("pub_year"),
            seed.get("title"),
            seed.get("passage_id"),
        )

    if not generation_3_seeds:
        logger.warning("No Generation 3 seeds selected; skipping.")
    else:
        generation_3_thread_id = str(uuid4())

        logger.info("=" * 72)
        logger.info("GENERATION 3: FORWARD EXPANSION (1901–2000)")
        logger.info("=" * 72)

        generation_3_result = workflow.invoke(
            {
                "seed_passages": generation_3_seeds,
                "forward_start_year": 1901,
                "forward_end_year": 2000,
                "representation": "l8",
                "forward_scale": "broad",
                "transfer_limit": 10,
            },
            config={
                "configurable": {
                    "thread_id": generation_3_thread_id,
                }
            },
        )

        logger.info(
            "Generation 3 passages: %d",
            len(generation_3_result["passages"]),
        )
        logger.info(
            "Generation 3 edges: %d",
            len(generation_3_result["edges"]),
        )

        retrieval_graph_3 = build_retrieval_graph(
            result=generation_3_result,
            search_direction="forward",
            generation=3,
            search_id=generation_3_thread_id,
        )

        logger.info(
            "Generation 3 graph: %d nodes, %d edges",
            len(retrieval_graph_3["nodes"]),
            len(retrieval_graph_3["edges"]),
        )

        classification_3, prospects_3 = classify_and_select_prospects(
            passages=retrieval_graph_3["nodes"],
            retrieval_graph=retrieval_graph_3,
            per_feature_limit=10,
        )

        log_prospects(
            "GENERATION 3 PROSPECTS",
            prospects_3,
        )


    # ---------------------------------------------------------
    # MERGE ALL GENERATIONS
    # ---------------------------------------------------------

    cumulative_graph = merge_retrieval_graphs(
        retrieval_graph_0,
        retrieval_graph_1,
    )

    if retrieval_graph_2 is not None:
        cumulative_graph = merge_retrieval_graphs(
            cumulative_graph,
            retrieval_graph_2,
        )

    if retrieval_graph_3 is not None:
        cumulative_graph = merge_retrieval_graphs(
            cumulative_graph,
            retrieval_graph_3,
        )

    # ---------------------------------------------------------
    # CUMULATIVE CLASSIFICATION DATA
    # ---------------------------------------------------------

    all_classification_results = [
        classification_0,
        classification_1,
        classification_2,
        classification_3,
    ]

    attach_classifications(
        retrieval_graph=cumulative_graph,
        classification_results=all_classification_results,
    )

    # ---------------------------------------------------------
    # CUMULATIVE REPORT
    # ---------------------------------------------------------

    log_cumulative_report(
        graph=cumulative_graph,
        classification_results=all_classification_results,
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

    logger.info(
        "Total nodes: %d",
        len(cumulative_graph["nodes"]),
    )
    logger.info(
        "Total edges: %d",
        len(cumulative_graph["edges"]),
    )
    logger.info(
        "Searches: %d",
        cumulative_graph["metadata"]["search_count"],
    )
    logger.info(
        "Convergence points: %d",
        len(cumulative_graph["convergence"]),
    )

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

    # ---------------------------------------------------------
    # ISOLATED NODE REPORT
    # ---------------------------------------------------------

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
