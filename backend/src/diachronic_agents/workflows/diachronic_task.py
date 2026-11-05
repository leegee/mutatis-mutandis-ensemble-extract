
from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import dataclass
from uuid import uuid4

from diachronic_agents.workflows.search_result import SearchResult
from diachronic_agents.workflows.forward_search import build_forward_search_workflow
from diachronic_agents.workflows.reverse_search import build_reverse_search_workflow
from diachronic_agents.retrieval.passage_retriever import PassageRetriever
from diachronic_agents.retrieval.retrieval_graph import build_retrieval_graph, merge_retrieval_graphs
from diachronic_agents.llm.passage_classifier import classify_passages
from diachronic_agents.retrieval.prospect_selector import select_prospects, rank_prospects_by_convergence
from diachronic_agents.visualization.graph_visualizer import visualise_retrieval_graph, report_isolated_nodes
from diachronic_agents.classification_configs import ALBINISM_CONFIG
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR

logger = get_logger(__name__)


def generate_periods(
    start_year: int,
    end_year: int,
    period_size: int,
    *,
    direction: str = "forward",
    first_period_size: int | None = None,
) -> list[tuple[int, int]]:
    """Generate contiguous, inclusive year ranges."""

    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")

    if direction not in {"forward", "reverse"}:
        raise ValueError("direction must be 'forward' or 'reverse'")

    if period_size < 1:
        raise ValueError("period_size must be positive")

    if first_period_size is not None and first_period_size < 1:
        raise ValueError("first_period_size must be positive")

    periods = []

    if direction == "forward":
        current_year = start_year
        current_size = first_period_size or period_size

        while current_year <= end_year:
            period_end = min(
                current_year + current_size - 1,
                end_year,
            )

            periods.append((current_year, period_end))
            current_year = period_end + 1
            current_size = period_size

    else:
        current_year = end_year
        current_size = first_period_size or period_size

        while current_year >= start_year:
            period_start = max(
                current_year - current_size + 1,
                start_year,
            )

            periods.append((period_start, current_year))
            current_year = period_start - 1
            current_size = period_size

    return periods


def _classification_fields(item: Any) -> dict:
    """Normalise a classification item from either a dict or object."""

    if isinstance(item, dict):
        return {
            "passage_id": item.get("passage_id"),
            "classification": item.get("classification"),
            "feature_type": item.get("feature_type"),
            "reason": item.get("reason"),
        }

    return {
        "passage_id": item.passage_id,
        "classification": item.classification,
        "feature_type": item.feature_type,
        "reason": item.reason,
    }


def _classification_items(result: Any) -> list:
    """Return classification items from a classification result."""

    if result is None:
        return []

    if isinstance(result, dict):
        return result.get("classifications", [])

    return getattr(result, "classifications", [])


def classify_and_select_prospects(
    passages: list[dict],
    retrieval_graph: dict,
    *,
    config: Any = ALBINISM_CONFIG,
    feature_types: set[str] | None = None,
    per_feature_limit: int = 10,
) -> tuple[Any, list[dict]]:
    """Classify passages, select relevant features, and rank by convergence."""

    if feature_types is None:
        feature_types = {"human_hair", "complexion"}

    classification_result = classify_passages(
        passages=passages,
        config=config,
    )

    prospects = select_prospects(
        passages=passages,
        classification_result=classification_result,
        feature_types=feature_types,
        per_feature_limit=per_feature_limit,
    )

    prospects = rank_prospects_by_convergence(
        prospects=prospects,
        retrieval_graph=retrieval_graph,
    )

    return classification_result, prospects


def log_prospects(
    title: str,
    prospects: list[dict],
) -> None:
    """Log ranked prospects."""

    logger.debug(title)

    for index, prospect in enumerate(prospects, start=1):
        logger.debug(
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


def collect_expansion_candidates(
    results: dict[int, dict],
    prospects: dict[int, list[dict]],
    period_indices: list[int],
) -> tuple[list[dict], list[dict]]:
    """
    Collect prospects that were actually discovered in the specified
    periods, excluding passages that were merely input seeds.

    Periods should be supplied newest first. This makes all_previous
    prefer more recently discovered passages.
    """

    candidate_prospects = []
    candidate_passages = {}

    seen_ids = set()

    for period_index in period_indices:
        result = results[period_index]

        # A passage is a discovery in this period only if it was
        # retrieved as the target of an actual retrieval edge.
        discovered_ids = {
            edge["target_passage_id"]
            for edge in result.get("edges", [])
            if edge.get("target_passage_id")
        }

        passages_by_id = {
            passage["passage_id"]: passage
            for passage in result.get("passages", [])
            if passage.get("passage_id")
        }

        for prospect in prospects.get(period_index, []):
            passage_id = prospect.get("passage_id")

            if not passage_id:
                continue

            if passage_id not in discovered_ids:
                continue

            if passage_id in seen_ids:
                continue

            passage = passages_by_id.get(passage_id)

            if passage is None:
                logger.warning(
                    "Cannot use prospect %s from period %d: "
                    "passage not found",
                    passage_id,
                    period_index,
                )
                continue

            candidate_prospects.append(prospect)
            candidate_passages[passage_id] = passage
            seen_ids.add(passage_id)

    logger.debug(
        "Expansion candidates: %d from periods %s",
        len(candidate_prospects),
        period_indices,
    )

    return candidate_prospects, list(candidate_passages.values())

   
def select_expansion_seeds(
    prospects: list[dict],
    passages: list[dict],
    count: int = 3,
) -> list[dict]:
    """Select passages from the current period for the next expansion."""

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

    logger.debug("Expansion seeds: %d", len(seeds))

    for seed in seeds:
        logger.debug(
            "EXPANSION SEED | year=%s | %s | %s",
            seed.get("pub_year"),
            seed.get("title"),
            seed.get("passage_id"),
        )

    return seeds


def attach_classifications(
    retrieval_graph: dict,
    classification_results: list,
) -> dict:
    """Attach passage classifications to their corresponding graph nodes."""

    classifications_by_id = {}

    for result in classification_results:
        for item in _classification_items(result):
            fields = _classification_fields(item)
            passage_id = fields["passage_id"]

            if passage_id is None:
                continue

            classifications_by_id[passage_id] = {
                "classification": fields["classification"],
                "feature_type": fields["feature_type"],
                "classification_reason": fields["reason"],
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
        for item in _classification_items(result):
            fields = _classification_fields(item)
            passage_id = fields["passage_id"]

            if passage_id is None:
                continue

            classifications_by_id.setdefault(
                passage_id,
                {
                    "classification": fields["classification"],
                    "feature_type": fields["feature_type"],
                    "reason": fields["reason"],
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

    logger.debug("=" * 100)
    logger.debug("CUMULATIVE CHRONOLOGICAL PASSAGE REPORT")
    logger.debug("=" * 100)

    for node in nodes:
        passage_id = node.get("passage_id", node["id"])
        classification = classifications_by_id.get(passage_id, {})

        logger.debug(
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
            logger.debug("       REASON: %s", classification["reason"])

    logger.debug("=" * 100)
    logger.debug("CUMULATIVE EDGE REPORT")
    logger.debug("=" * 100)

    nodes_by_id = {
        node["id"]: node
        for node in graph["nodes"]
    }

    logger.debug("=" * 100)
    logger.debug("CROSS-GENERATION EDGE REPORT")
    logger.debug("=" * 100)

    for edge in graph["edges"]:
        source = nodes_by_id.get(edge["source"])
        target = nodes_by_id.get(edge["target"])

        if source is None or target is None:
            continue

        source_generation = source.get("generation", "?")
        target_generation = target.get("generation", "?")
        edge_generation = edge.get("generation", "?")

        if source_generation != target_generation:
            logger.debug(
                "CROSS-GENERATION EDGE | "
                "edge_gen=%s | source_gen=%s | target_gen=%s | "
                "%s (%s) -> %s (%s)",
                edge_generation,
                source_generation,
                target_generation,
                source.get("pub_year", "?"),
                source.get("title", "Untitled"),
                target.get("pub_year", "?"),
                target.get("title", "Untitled"),
            )


    logger.debug("=" * 100)
    logger.debug("GENERATION CONNECTIVITY REPORT")
    logger.debug("=" * 100)

    connectivity_counts = {
        "adjacent": 0,
        "older_source": 0,
        "other": 0,
    }

    for edge in graph["edges"]:
        source = nodes_by_id.get(edge["source"])
        target = nodes_by_id.get(edge["target"])

        if source is None or target is None:
            continue

        source_generation = source.get("generation")
        target_generation = target.get("generation")
        edge_generation = edge.get("generation")

        if (
            source_generation == edge_generation
            and target_generation == edge_generation + 1
        ):
            connectivity = "ADJACENT"
            connectivity_counts["adjacent"] += 1

        elif (
            isinstance(source_generation, int)
            and isinstance(edge_generation, int)
            and source_generation < edge_generation
        ):
            connectivity = "OLDER SOURCE"
            connectivity_counts["older_source"] += 1

        else:
            connectivity = "OTHER"
            connectivity_counts["other"] += 1

        if connectivity != "ADJACENT":
            logger.debug(
                "%s | edge_gen=%s | source_gen=%s | target_gen=%s | "
                "%s (%s) -> %s (%s)",
                connectivity,
                edge_generation,
                source_generation,
                target_generation,
                source.get("pub_year", "?"),
                source.get("title", "Untitled"),
                target.get("pub_year", "?"),
                target.get("title", "Untitled"),
            )

    logger.debug(
        "CONNECTIVITY TOTALS | adjacent=%d | older_source=%d | other=%d",
        connectivity_counts["adjacent"],
        connectivity_counts["older_source"],
        connectivity_counts["other"],
    )

    logger.debug("=" * 100)
    logger.debug("CONVERGENCE REPORT")
    logger.debug("=" * 100)

    nodes_by_id = {node["id"]: node for node in nodes}

    for item in graph["convergence"]:
        target = nodes_by_id.get(item["target_passage_id"])

        if target is None:
            continue

        logger.debug(
            "CONVERGENCE | %s | %s | %d incoming sources",
            target.get("pub_year", "?"),
            target.get("title", "Untitled"),
            item["source_count"],
        )

    logger.debug("=" * 100)


def merge_all_graphs(graphs: dict[int, dict]) -> dict:
    """Merge all period graphs into one cumulative graph."""

    cumulative_graph = {}

    for period_index in sorted(graphs):
        graph = graphs[period_index]

        cumulative_graph = merge_retrieval_graphs(
            cumulative_graph,
            graph,
        )

    if not cumulative_graph:
        raise ValueError("No retrieval graphs were produced")

    return cumulative_graph


def run_diachronic_search(
    *,
    query: str,
    initial_period: tuple[int, int],
    target_period: tuple[int, int],
    period_size: int = 50,
    direction: str = "forward",
    first_period_size: int | None = None,
    representation: str = "l8",
    scale: str = "broad",
    initial_limit: int = 20,
    seed_limit: int = 3,
    transfer_limit: int = 10,
    expansion_seed_count: int = 3,
    seed_strategy: str = "previous_period",
    prospect_limit: int = 10,
    feature_types: set[str] | None = None,
    classification_config: Any = ALBINISM_CONFIG,
    workflow: Any = None,
    retriever: PassageRetriever | None = None,
    checkpointer: Any = None,
    log_report: bool = True,
) -> SearchResult:
    """
    Run a multi-period forward or reverse diachronic search.

    The initial query retrieves passages from initial_period and searches
    those passages into the first target period.

    Each subsequent period is searched using prospects selected from
    the preceding period.

    Period boundaries are inclusive.
    """

    initial_start, initial_end = initial_period
    target_start, target_end = target_period

    if direction not in {"forward", "reverse"}:
        raise ValueError("direction must be 'forward' or 'reverse'")

    if initial_start > initial_end:
        raise ValueError("Invalid initial_period")

    if target_start > target_end:
        raise ValueError("Invalid target_period")

    if direction == "forward" and target_start <= initial_end:
        raise ValueError(
            "For forward searches, target_period must begin "
            "after initial_period ends"
        )

    if direction == "reverse" and target_end >= initial_start:
        raise ValueError(
            "For reverse searches, target_period must end "
            "before initial_period begins"
        )

    if expansion_seed_count < 1:
        raise ValueError("expansion_seed_count must be positive")

    if seed_strategy not in {"previous_period", "all_previous"}:
        raise ValueError( "seed_strategy must be 'previous_period' or 'all_previous'" )
        
    if initial_limit < 1 or seed_limit < 1 or transfer_limit < 1:
        raise ValueError("Search limits must be positive")

    if prospect_limit < 1:
        raise ValueError("prospect_limit must be positive")

    periods = generate_periods(
        target_start,
        target_end,
        period_size,
        direction=direction,
        first_period_size=first_period_size,
    )

    if workflow is None:
        if direction == "forward":
            workflow = build_forward_search_workflow(
                retriever=retriever,
                checkpointer=checkpointer,
            )
        else:
            workflow = build_reverse_search_workflow(
                retriever=retriever,
                checkpointer=checkpointer,
            )

    results = {}
    graphs = {}
    classifications = {}
    prospects = {}

    logger.debug("=" * 80)
    logger.debug("DIACHRONIC SEARCH")
    logger.debug("=" * 80)
    logger.debug("Direction: %s", direction.upper())
    logger.debug("Query: %s", query)
    logger.debug("Initial period: %d–%d", initial_start, initial_end)
    logger.debug("Target period: %d–%d", target_start, target_end)
    logger.debug("Generated periods: %s", periods)
    logger.debug("Seed strategy: %s", seed_strategy)
    logger.debug("Representation: %s", representation)
    logger.debug("Scale: %s", scale)

    for period_index, (period_start, period_end) in enumerate(periods):
        thread_id = str(uuid4())

        logger.debug("=" * 80)
        logger.debug(
            "PERIOD %d: %s SEARCH (%d–%d)",
            period_index,
            direction.upper(),
            period_start,
            period_end,
        )
        logger.debug("=" * 80)

        # The lower-level workflows share the same common state fields,
        # but use direction-specific period and scale field names.
        period_inputs = {
            f"{direction}_start_year": period_start,
            f"{direction}_end_year": period_end,
            f"{direction}_scale": scale,
        }

        inputs = {
            "representation": representation,
            "transfer_limit": transfer_limit,
            **period_inputs,
        }

        if period_index == 0:
            inputs.update({
                "query": query,
                "initial_start_year": initial_start,
                "initial_end_year": initial_end,
                "initial_scale": scale,
                "initial_limit": initial_limit,
                "seed_limit": seed_limit,
            })

        else:
            if seed_strategy == "previous_period":
                candidate_periods = [period_index - 1]
            else:
                candidate_periods = list(
                    range(period_index - 1, -1, -1)
                )

            candidate_prospects, candidate_passages = (
                collect_expansion_candidates(
                    results=results,
                    prospects=prospects,
                    period_indices=candidate_periods,
                )
            )

            seed_passages = select_expansion_seeds(
                prospects=candidate_prospects,
                passages=candidate_passages,
                count=expansion_seed_count,
            )

            if not seed_passages:
                logger.warning(
                    "No expansion seeds for period %d; stopping search.",
                    period_index,
                )
                break

            inputs["seed_passages"] = seed_passages

        result = workflow.invoke(
            inputs,
            config={"configurable": {"thread_id": thread_id}},
        )

        results[period_index] = result

        logger.debug(
            "Period %d results: %d passages, %d edges",
            period_index,
            len(result["passages"]),
            len(result["edges"]),
        )

        graph = build_retrieval_graph(
            result=result,
            search_direction=direction,
            generation=period_index,
            search_id=thread_id,
        )

        graphs[period_index] = graph

        logger.debug(
            "Period %d graph: %d nodes, %d edges",
            period_index,
            len(graph["nodes"]),
            len(graph["edges"]),
        )

        classification, period_prospects = classify_and_select_prospects(
            passages=graph["nodes"],
            retrieval_graph=graph,
            config=classification_config,
            feature_types=feature_types,
            per_feature_limit=prospect_limit,
        )

        classifications[period_index] = classification
        prospects[period_index] = period_prospects

        log_prospects(
            f"PERIOD {period_index} PROSPECTS "
            f"({period_start}–{period_end})",
            period_prospects,
        )

    cumulative_graph = merge_all_graphs(graphs)
    logger.debug(
        "CUMULATIVE GRAPH METADATA: %s",
        cumulative_graph.get("metadata"),
    )

    logger.debug(
        "PERIOD GRAPH METADATA: %s",
        {
            index: graph.get("metadata")
            for index, graph in graphs.items()
        },
    )

    attach_classifications(
        retrieval_graph=cumulative_graph,
        classification_results=list(classifications.values()),
    )

    if log_report:
        log_cumulative_report(
            graph=cumulative_graph,
            classification_results=list(classifications.values()),
        )

        report_isolated_nodes(cumulative_graph)

    # Preserve the requested range as search provenance.
    searched_periods = periods[:len(results)]

    if direction == "reverse":
        requested_start = min(
            period[0] for period in searched_periods
        )
        requested_end = max(initial_end, max(
            period[1] for period in searched_periods
        ))
    else:
        requested_start = min(initial_start, min(
            period[0] for period in searched_periods
        ))
        requested_end = max(
            period[1] for period in searched_periods
        )

    # Use actual dated evidence for the visual boundaries.
    dated_years = [
        int(node["pub_year"])
        for node in cumulative_graph["nodes"]
        if node.get("pub_year") is not None
    ]

    if dated_years:
        search_start = min(dated_years)
        search_end = max(dated_years)
    else:
        search_start = requested_start
        search_end = requested_end

    cumulative_graph.setdefault("metadata", {})["requested_search_range"] = {
        "start": requested_start,
        "end": requested_end,
    }

    cumulative_graph["metadata"]["seed_strategy"] = seed_strategy
    cumulative_graph["metadata"]["query"] = query
    cumulative_graph["metadata"]["direction"] = direction

    cumulative_graph.setdefault("metadata", {})["search_range"] = {
        "start": search_start,
        "end": search_end,
    }

    logger.debug("=" * 80)
    logger.debug("DIACHRONIC SEARCH COMPLETE")
    logger.debug("=" * 80)
    logger.debug("Direction: %s", direction.upper())
    logger.debug("Periods completed: %d / %d", len(results), len(periods))
    logger.debug("Total nodes: %d", len(cumulative_graph["nodes"]))
    logger.debug("Total edges: %d", len(cumulative_graph["edges"]))
    
    metadata = cumulative_graph.get("metadata", {})
    search_count = metadata.get( "search_count", len(metadata.get("search_runs", [])), )
    logger.debug("Searches: %d", search_count)

    logger.debug( "Convergence points: %d", len(cumulative_graph["convergence"]), )

    return SearchResult(
        query=query,
        direction=direction,
        initial_period=initial_period,
        target_period=target_period,
        periods=periods,
        results=results,
        graphs=graphs,
        classifications=classifications,
        prospects=prospects,
        cumulative_graph=cumulative_graph,
    )

