"""
base_search.py - Shared mechanics for forward and reverse diachronic search.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from diachronic_agents.retrieval.passage_retriever import PassageRetriever


SearchDirection = Literal["forward", "reverse"]


class SearchTask(TypedDict):
    seed: dict[str, Any]
    seed_index: int
    representation: str
    search_start_year: int
    search_end_year: int
    transfer_limit: int
    search_scale: str


class SearchState(TypedDict, total=False):
    # Inputs
    direction: SearchDirection
    query: str
    initial_start_year: int
    initial_end_year: int
    forward_start_year: int
    forward_end_year: int
    reverse_start_year: int
    reverse_end_year: int
    representation: str
    initial_scale: str
    forward_scale: str
    reverse_scale: str
    initial_limit: int
    seed_limit: int
    transfer_limit: int
    overlap_threshold: float
    seed_passages: list[dict[str, Any]]

    # Intermediate results
    initial_results: list[dict[str, Any]]
    seeds: list[dict[str, Any]]
    search_results: Annotated[
        list[dict[str, Any]],
        operator.add,
    ]
    warnings: list[str]

    # Final output
    seed_ids: list[str]
    passages: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    deduplicated_edges: list[dict[str, Any]]
    document_diverse_edges: list[dict[str, Any]]
    overlap_suppressed_edges: list[dict[str, Any]]
    initial_period: list[int]
    forward_period: list[int]
    reverse_period: list[int]


# -------------------------------------------------------------
# Document and passage helpers
# -------------------------------------------------------------

def document_key(hit: dict[str, Any]) -> tuple[str, str]:
    """Return a stable identity for a source document."""

    doc_id = hit.get("doc_id")

    if doc_id:
        return str(hit.get("corpus") or ""), str(doc_id)

    # Without document identity, passages must remain distinct.
    return "passage", str(hit.get("passage_id"))


def token_span(
    hit: dict[str, Any],
) -> tuple[int, int] | None:
    """Return a passage's token interval as a half-open interval."""

    possible_fields = (
        ("token_start", "token_end"),
        ("token_start_idx", "token_end_idx"),
        ("token_idx_start", "token_idx_end"),
    )

    for start_field, end_field in possible_fields:
        start = hit.get(start_field)
        end = hit.get(end_field)

        if start is None or end is None:
            continue

        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            continue

        if end > start:
            return start, end

    return None


def overlap_ratio(
    span_a: tuple[int, int],
    span_b: tuple[int, int],
) -> float:
    """Intersection divided by the shorter passage length."""

    start_a, end_a = span_a
    start_b, end_b = span_b

    intersection = max(
        0,
        min(end_a, end_b) - max(start_a, start_b),
    )

    shorter_length = min(
        end_a - start_a,
        end_b - start_b,
    )

    return intersection / shorter_length if shorter_length > 0 else 0.0


def ranking_key(edge: dict[str, Any]) -> tuple[float, float]:
    """Sort best-ranked retrievals first."""

    rank = edge.get("rank")
    distance = edge.get("distance")

    return (
        float(rank) if rank is not None else float("inf"),
        float(distance) if distance is not None else float("inf"),
    )


# -------------------------------------------------------------
# Passage-window deduplication
# -------------------------------------------------------------

def deduplicate_overlapping_edges(
    edges: list[dict[str, Any]],
    passages: dict[str, dict[str, Any]],
    threshold: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    """Deduplicate overlapping passage windows independently per seed."""

    edges_by_seed: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        edges_by_seed.setdefault(
            edge["source_passage_id"], []
        ).append(edge)

    retained_edges = []
    suppressed_edges = []
    warnings = []
    missing_span_ids = set()

    for seed_edges in edges_by_seed.values():
        ordered_edges = sorted(seed_edges, key=ranking_key)

        retained_for_seed = []

        for edge in ordered_edges:
            target_id = edge["target_passage_id"]
            hit = passages.get(target_id)

            if hit is None:
                retained_edges.append(edge)
                continue

            candidate_span = token_span(hit)

            if candidate_span is None:
                retained_edges.append(edge)

                if target_id not in missing_span_ids:
                    missing_span_ids.add(target_id)
                    warnings.append(
                        f"Could not deduplicate passage {target_id[:12]}: "
                        "no usable token span."
                    )

                continue

            candidate_document = document_key(hit)
            duplicate_of = None
            duplicate_overlap = None

            for retained_edge, retained_hit, retained_span in retained_for_seed:
                if document_key(retained_hit) != candidate_document:
                    continue

                overlap = overlap_ratio(candidate_span, retained_span)

                if overlap >= threshold:
                    duplicate_of = retained_edge
                    duplicate_overlap = overlap
                    break

            if duplicate_of is not None:
                suppressed_edges.append({
                    **edge,
                    "overlap_ratio": duplicate_overlap,
                    "retained_target_passage_id": (
                        duplicate_of["target_passage_id"]
                    ),
                })
                continue

            retained_edges.append(edge)
            retained_for_seed.append((edge, hit, candidate_span))

    return retained_edges, suppressed_edges, warnings


def select_document_diverse_edges(
    edges: list[dict[str, Any]],
    passages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the best-ranked passage from each document per seed."""

    edges_by_seed: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        edges_by_seed.setdefault(
            edge["source_passage_id"], []
        ).append(edge)

    selected = []

    for seed_edges in edges_by_seed.values():
        ordered_edges = sorted(seed_edges, key=ranking_key)
        seen_documents = set()

        for edge in ordered_edges:
            hit = passages.get(edge["target_passage_id"])

            if hit is None:
                selected.append(edge)
                continue

            key = document_key(hit)

            if key in seen_documents:
                continue

            seen_documents.add(key)
            selected.append(edge)

    return selected


# -------------------------------------------------------------
# Seed selection
# -------------------------------------------------------------

def select_seeds(
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Select the highest-ranked passage from each distinct document."""

    selected = []
    seen_documents = set()

    for hit in results:
        key = document_key(hit)

        if key in seen_documents:
            continue

        seen_documents.add(key)
        selected.append(hit)

        if len(selected) >= limit:
            break

    return selected


# -------------------------------------------------------------
# Input validation
# -------------------------------------------------------------

def validate_inputs(
    inputs: dict[str, Any],
    direction: SearchDirection,
) -> dict[str, Any]:
    """Validate common and direction-specific search inputs."""

    values = dict(inputs)
    values["direction"] = direction

    seed_passages = values.get("seed_passages")

    if seed_passages:
        seed_passages = [dict(passage) for passage in seed_passages]

        if any(not passage.get("passage_id") for passage in seed_passages):
            raise ValueError("Every explicit seed must have a passage_id")

        # Preserve input order while deduplicating.
        seeds_by_id = {
            passage["passage_id"]: passage
            for passage in reversed(seed_passages)
        }
        seed_passages = list(reversed(list(seeds_by_id.values())))

        values["seed_passages"] = seed_passages
        values.setdefault("query", "explicit seeds")

        seed_years = [
            int(passage["pub_year"])
            for passage in seed_passages
            if passage.get("pub_year") is not None
        ]

        if seed_years:
            values.setdefault("initial_start_year", min(seed_years))
            values.setdefault("initial_end_year", max(seed_years))

    else:
        values["seed_passages"] = []

        required = (
            "query",
            "initial_start_year",
            "initial_end_year",
        )

        missing = [name for name in required if name not in values]

        if missing:
            raise ValueError(
                f"Missing workflow inputs: {', '.join(missing)}"
            )

    period_fields = (
        ("forward_start_year", "forward_end_year")
        if direction == "forward"
        else ("reverse_start_year", "reverse_end_year")
    )

    required = (
        "initial_start_year",
        "initial_end_year",
        *period_fields,
    )

    missing = [name for name in required if name not in values]

    if missing:
        raise ValueError(
            f"Missing workflow inputs: {', '.join(missing)}"
        )

    for name in required:
        values[name] = int(values[name])

    initial_start = values["initial_start_year"]
    initial_end = values["initial_end_year"]
    search_start = values[period_fields[0]]
    search_end = values[period_fields[1]]

    if initial_start > initial_end:
        raise ValueError("Invalid initial year interval")

    if search_start > search_end:
        raise ValueError("Invalid search year interval")

    if direction == "forward":
        if search_start <= initial_end:
            raise ValueError(
                "The forward interval must start after "
                "the initial interval ends"
            )
    else:
        if search_end >= initial_start:
            raise ValueError(
                "The reverse interval must end before "
                "the initial interval starts"
            )

    values.setdefault("representation", "l8")
    values.setdefault("initial_scale", "broad")
    values.setdefault(
        f"{direction}_scale",
        values["initial_scale"],
    )
    values.setdefault("initial_limit", 20)
    values.setdefault("seed_limit", 3)
    values.setdefault("transfer_limit", 10)
    values.setdefault("overlap_threshold", 0.80)

    for name in ("initial_limit", "seed_limit", "transfer_limit"):
        values[name] = int(values[name])

        if values[name] < 1:
            raise ValueError(f"{name} must be positive")

    values["overlap_threshold"] = float(values["overlap_threshold"])

    if not 0 < values["overlap_threshold"] <= 1:
        raise ValueError(
            "overlap_threshold must be greater than 0 "
            "and no greater than 1"
        )

    if (
        not values["seed_passages"]
        and values["seed_limit"] > values["initial_limit"]
    ):
        raise ValueError("seed_limit cannot exceed initial_limit")

    values["query"] = str(values["query"]).strip()

    return values


# -------------------------------------------------------------
# Generic workflow builder
# -------------------------------------------------------------

def build_search_workflow(
    direction: SearchDirection,
    retriever: PassageRetriever | None = None,
    *,
    checkpointer=None,
):
    """Build a forward or reverse diachronic search workflow."""

    if direction not in ("forward", "reverse"):
        raise ValueError(f"Unsupported search direction: {direction}")

    retriever = retriever or PassageRetriever()
    checkpointer = checkpointer or InMemorySaver()

    period_fields = (
        ("forward_start_year", "forward_end_year")
        if direction == "forward"
        else ("reverse_start_year", "reverse_end_year")
    )

    scale_field = f"{direction}_scale"

    def initial_search_node(state: SearchState) -> dict[str, Any]:
        params = validate_inputs(state, direction)

        if params["seed_passages"]:
            return {
                **params,
                "initial_results": params["seed_passages"],
                "warnings": [],
            }

        outcome = retriever.search_text(
            query=params["query"],
            representation=params["representation"],
            start_year=params["initial_start_year"],
            end_year=params["initial_end_year"],
            limit=params["initial_limit"],
            scale=params["initial_scale"],
        )

        return {
            **params,
            "initial_results": outcome["results"],
            "warnings": list(outcome["warnings"]),
        }

    def select_seeds_node(state: SearchState) -> dict[str, Any]:
        if state.get("seed_passages"):
            seeds = state["seed_passages"]

            return {
                "seeds": seeds,
                "seed_ids": [seed["passage_id"] for seed in seeds],
                "warnings": list(state.get("warnings", [])),
            }

        seeds = select_seeds(
            state["initial_results"],
            state["seed_limit"],
        )

        warnings = list(state.get("warnings", []))

        if len(seeds) < state["seed_limit"]:
            warnings.append(
                f"Requested {state['seed_limit']} seeds, but found only "
                f"{len(seeds)} distinct documents in initial results."
            )

        return {
            "seeds": seeds,
            "seed_ids": [seed["passage_id"] for seed in seeds],
            "warnings": warnings,
        }

    def search_node(task: SearchTask) -> dict[str, Any]:
        seed = task["seed"]

        outcome = retriever.search_from_passage(
            passage_id=seed["passage_id"],
            representation=task["representation"],
            start_year=task["search_start_year"],
            end_year=task["search_end_year"],
            limit=task["transfer_limit"],
            scale=task["search_scale"],
        )

        return {
            "search_results": [{
                "seed": seed,
                "seed_index": task["seed_index"],
                "outcome": outcome,
            }]
        }

    def dispatch_searches(state: SearchState) -> list[Send] | str:
        if not state["seeds"]:
            return "merge_results"

        return [
            Send(
                "search_passages",
                {
                    "seed": seed,
                    "seed_index": index,
                    "representation": state["representation"],
                    "search_start_year": state[period_fields[0]],
                    "search_end_year": state[period_fields[1]],
                    "transfer_limit": state["transfer_limit"],
                    "search_scale": state[scale_field],
                },
            )
            for index, seed in enumerate(state["seeds"])
        ]

    def merge_results_node(state: SearchState) -> dict[str, Any]:
        passages = {
            hit["passage_id"]: hit
            for hit in state["initial_results"]
        }

        warnings = list(state.get("warnings", []))
        edges = []

        for item in sorted(
            state.get("search_results", []),
            key=lambda item: item["seed_index"],
        ):
            seed = item["seed"]
            outcome = item["outcome"]

            warnings.extend(outcome["warnings"])

            for hit in outcome["results"]:
                passages.setdefault(hit["passage_id"], hit)

                edges.append({
                    "source_passage_id": seed["passage_id"],
                    "target_passage_id": hit["passage_id"],
                    "source_pub_year": seed.get("pub_year"),
                    "target_pub_year": hit.get("pub_year"),
                    "source_scale": seed.get("scale"),
                    "target_scale": hit.get("scale"),
                    "representation": state["representation"],
                    "rank": hit.get("rank"),
                    "distance": hit.get("distance"),
                    "score": hit.get("score"),
                    "source_period": [
                        state["initial_start_year"],
                        state["initial_end_year"],
                    ],
                    "target_period": [
                        state[period_fields[0]],
                        state[period_fields[1]],
                    ],
                    "search_direction": direction,
                })

        deduplicated, suppressed, dedup_warnings = (
            deduplicate_overlapping_edges(
                edges,
                passages,
                state["overlap_threshold"],
            )
        )

        warnings.extend(dedup_warnings)

        document_diverse = select_document_diverse_edges(
            deduplicated,
            passages,
        )

        initial_period = [
            state["initial_start_year"],
            state["initial_end_year"],
        ]

        search_period = [
            state[period_fields[0]],
            state[period_fields[1]],
        ]

        return {
            "passages": list(passages.values()),
            "edges": edges,
            "deduplicated_edges": deduplicated,
            "document_diverse_edges": document_diverse,
            "overlap_suppressed_edges": suppressed,
            "warnings": warnings,
            "initial_period": initial_period,
            "forward_period": search_period if direction == "forward" else [],
            "reverse_period": search_period if direction == "reverse" else [],
        }

    builder = StateGraph(SearchState)

    builder.add_node("initial_search", initial_search_node)
    builder.add_node("select_seeds", select_seeds_node)
    builder.add_node("search_passages", search_node)
    builder.add_node("merge_results", merge_results_node)

    builder.add_edge(START, "initial_search")
    builder.add_edge("initial_search", "select_seeds")

    builder.add_conditional_edges(
        "select_seeds",
        dispatch_searches,
        ["search_passages", "merge_results"],
    )

    builder.add_edge("search_passages", "merge_results")
    builder.add_edge("merge_results", END)

    return builder.compile(checkpointer=checkpointer)

