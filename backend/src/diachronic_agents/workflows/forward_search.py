
# forward_search.py
#
# Forward diachronic search.
# Overlapping passage windows are deduplicated after retrieval,
# while all original seed-to-passage retrieval edges are preserved.

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from diachronic_agents.retrieval.passage_retriever import PassageRetriever


class ForwardSearchTask(TypedDict):
    seed: dict[str, Any]
    seed_index: int
    representation: str
    forward_start_year: int
    forward_end_year: int
    transfer_limit: int
    forward_scale: str


class ForwardSearchState(TypedDict, total=False):
    # Inputs
    query: str
    initial_start_year: int
    initial_end_year: int
    forward_start_year: int
    forward_end_year: int
    representation: str
    initial_scale: str
    forward_scale: str
    initial_limit: int
    seed_limit: int
    transfer_limit: int
    overlap_threshold: float
    seed_passages: list[dict[str, Any]]

    # Intermediate results
    initial_results: list[dict[str, Any]]
    seeds: list[dict[str, Any]]
    forward_results: Annotated[
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


# -------------------------------------------------------------
# General helpers
# -------------------------------------------------------------

def _document_key(hit: dict[str, Any]) -> tuple[str, str]:
    """Return a stable identity for a source document."""

    doc_id = hit.get("doc_id")

    if doc_id:
        return (
            str(hit.get("corpus") or ""),
            str(doc_id),
        )

    # If document identity is unavailable, do not merge passages.
    return ("passage", str(hit.get("passage_id")))


def _token_span(
    hit: dict[str, Any],
) -> tuple[int, int] | None:
    """
    Return a passage's token interval as (start, end).

    Intervals are treated as half-open:
        start is included
        end is excluded

    The first pair is the expected naming convention. The
    alternatives allow for minor differences in result schemas.
    """

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
            start = int(start)
            end = int(end)
        except (TypeError, ValueError):
            continue

        if end > start:
            return start, end

    return None


def _overlap_ratio(
    span_a: tuple[int, int],
    span_b: tuple[int, int],
) -> float:
    """
    Calculate intersection divided by the shorter passage length.

    A value of 1.0 means the shorter passage is entirely contained
    within the longer passage.
    """

    start_a, end_a = span_a
    start_b, end_b = span_b

    intersection = max(
        0,
        min(end_a, end_b) - max(start_a, start_b),
    )

    length_a = end_a - start_a
    length_b = end_b - start_b

    shorter_length = min(length_a, length_b)

    if shorter_length <= 0:
        return 0.0

    return intersection / shorter_length


def _ranking_key(edge: dict[str, Any]) -> tuple[float, float]:
    """Sort best-ranked retrievals first."""

    rank = edge.get("rank")
    distance = edge.get("distance")

    rank_value = (
        float(rank)
        if rank is not None
        else float("inf")
    )

    distance_value = (
        float(distance)
        if distance is not None
        else float("inf")
    )

    return rank_value, distance_value


def _deduplicate_overlapping_edges(
    edges: list[dict[str, Any]],
    passages: dict[str, dict[str, Any]],
    threshold: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    """
    Deduplicate overlapping passage windows independently per seed.

    The best-ranked passage is retained. A lower-ranked passage
    is suppressed when it overlaps a retained passage from the
    same source document by at least the specified threshold.

    Original edges are not modified.
    """

    # Group edges by their originating seed.
    edges_by_seed: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        seed_id = edge["source_passage_id"]

        edges_by_seed.setdefault(seed_id, []).append(edge)

    retained_edges = []
    suppressed_edges = []
    warnings = []

    missing_span_ids = set()

    for seed_id, seed_edges in edges_by_seed.items():

        # Process the best-ranked passages first.
        ordered_edges = sorted(
            seed_edges,
            key=_ranking_key,
        )

        retained_for_seed: list[
            tuple[dict[str, Any], dict[str, Any], tuple[int, int]]
        ] = []

        for edge in ordered_edges:

            target_id = edge["target_passage_id"]
            hit = passages.get(target_id)

            if hit is None:
                retained_edges.append(edge)
                continue

            candidate_span = _token_span(hit)

            if candidate_span is None:
                retained_edges.append(edge)

                if target_id not in missing_span_ids:
                    missing_span_ids.add(target_id)
                    warnings.append(
                        "Could not deduplicate passage "
                        f"{target_id[:12]}: no usable token span."
                    )

                continue

            candidate_document = _document_key(hit)

            duplicate_of = None
            duplicate_overlap = None

            for retained_edge, retained_hit, retained_span in (
                retained_for_seed
            ):

                # Overlap only has meaning within the same document.
                if _document_key(retained_hit) != candidate_document:
                    continue

                overlap = _overlap_ratio(
                    candidate_span,
                    retained_span,
                )

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

            retained_for_seed.append((
                edge,
                hit,
                candidate_span,
            ))

    return retained_edges, suppressed_edges, warnings


def _select_document_diverse_edges(
    edges: list[dict[str, Any]],
    passages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Retain the best-ranked passage from each document per seed.

    This is applied after overlapping-window deduplication.
    """

    edges_by_seed: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        seed_id = edge["source_passage_id"]

        edges_by_seed.setdefault(seed_id, []).append(edge)

    selected = []

    for seed_edges in edges_by_seed.values():

        ordered_edges = sorted(
            seed_edges,
            key=_ranking_key,
        )

        seen_documents = set()

        for edge in ordered_edges:

            target_id = edge["target_passage_id"]
            hit = passages.get(target_id)

            if hit is None:
                selected.append(edge)
                continue

            document_key = _document_key(hit)

            if document_key in seen_documents:
                continue

            seen_documents.add(document_key)
            selected.append(edge)

    return selected


# -------------------------------------------------------------
# Input validation
# -------------------------------------------------------------

def _validate_inputs(inputs: dict[str, Any]) -> dict[str, Any]:

    values = dict(inputs)

    # Explicit-seed mode.
    seed_passages = values.get("seed_passages")

    if seed_passages:
        seed_passages = [
            dict(passage)
            for passage in seed_passages
        ]

        missing_ids = [
            passage
            for passage in seed_passages
            if not passage.get("passage_id")
        ]

        if missing_ids:
            raise ValueError(
                "Every explicit seed must have a passage_id"
            )

        # Deduplicate seed IDs without changing their order.
        seeds_by_id = {
            passage["passage_id"]: passage
            for passage in seed_passages
        }

        seed_passages = list(seeds_by_id.values())

        values["seed_passages"] = seed_passages
        values["query"] = values.get("query", "explicit seeds")

        seed_years = [
            int(passage["pub_year"])
            for passage in seed_passages
            if passage.get("pub_year") is not None
        ]

        if seed_years:
            values.setdefault(
                "initial_start_year",
                min(seed_years),
            )
            values.setdefault(
                "initial_end_year",
                max(seed_years),
            )

    else:
        values["seed_passages"] = []

        required = (
            "query",
            "initial_start_year",
            "initial_end_year",
        )

        missing = [
            name
            for name in required
            if name not in values
        ]

        if missing:
            raise ValueError(
                f"Missing workflow inputs: {', '.join(missing)}"
            )

    required = (
        "initial_start_year",
        "initial_end_year",
        "forward_start_year",
        "forward_end_year",
    )

    missing = [
        name
        for name in required
        if name not in values
    ]

    if missing:
        raise ValueError(
            f"Missing workflow inputs: {', '.join(missing)}"
        )

    for name in required:
        values[name] = int(values[name])

    if values["initial_start_year"] > values["initial_end_year"]:
        raise ValueError("Invalid initial year interval")

    if values["forward_start_year"] > values["forward_end_year"]:
        raise ValueError("Invalid forward year interval")

    if values["forward_start_year"] <= values["initial_end_year"]:
        raise ValueError(
            "The forward interval must start after "
            "the initial interval ends"
        )

    values.setdefault("representation", "l8")
    values.setdefault("initial_scale", "broad")
    values.setdefault("forward_scale", values["initial_scale"])
    values.setdefault("initial_limit", 20)
    values.setdefault("seed_limit", 3)
    values.setdefault("transfer_limit", 10)
    values.setdefault("overlap_threshold", 0.80)

    values["initial_limit"] = int(values["initial_limit"])
    values["seed_limit"] = int(values["seed_limit"])
    values["transfer_limit"] = int(values["transfer_limit"])
    values["overlap_threshold"] = float(
        values["overlap_threshold"]
    )

    if values["initial_limit"] < 1:
        raise ValueError("initial_limit must be positive")

    if values["seed_limit"] < 1:
        raise ValueError("seed_limit must be positive")

    if values["transfer_limit"] < 1:
        raise ValueError("transfer_limit must be positive")

    if (
        not values["seed_passages"]
        and values["seed_limit"] > values["initial_limit"]
    ):
        raise ValueError(
            "seed_limit cannot exceed initial_limit"
        )

    if not 0 < values["overlap_threshold"] <= 1:
        raise ValueError(
            "overlap_threshold must be greater than 0 "
            "and no greater than 1"
        )

    values["query"] = str(values["query"]).strip()

    return values


# -------------------------------------------------------------
# Seed selection
# -------------------------------------------------------------

def _select_seeds(
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Select the highest-ranked passage from each distinct document."""

    selected = []
    seen_documents = set()

    for hit in results:

        document_key = _document_key(hit)

        if document_key in seen_documents:
            continue

        seen_documents.add(document_key)
        selected.append(hit)

        if len(selected) >= limit:
            break

    return selected


# -------------------------------------------------------------
# Build the forward-search workflow
# -------------------------------------------------------------

def build_forward_search_workflow(
    retriever: PassageRetriever | None = None,
    *,
    checkpointer=None,
):

    retriever = retriever or PassageRetriever()
    checkpointer = checkpointer or InMemorySaver()

    # ---------------------------------------------------------
    # Node 1: initial textual search
    # ---------------------------------------------------------

    def initial_search_node(
        state: ForwardSearchState,
    ) -> dict[str, Any]:

        params = _validate_inputs(state)

        # Explicit-seed mode: no lexical search.
        if params["seed_passages"]:

            return {
                **params,
                "initial_results": params["seed_passages"],
                "warnings": [],
            }

        # Normal mode.
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

    # ---------------------------------------------------------
    # Node 2: select document-diverse seeds
    # ---------------------------------------------------------

    def select_seeds_node(
        state: ForwardSearchState,
    ) -> dict[str, Any]:

        # Explicit-seed mode.
        if state.get("seed_passages"):
            seeds = state["seed_passages"]

            return {
                "seeds": seeds,
                "seed_ids": [
                    seed["passage_id"]
                    for seed in seeds
                ],
                "warnings": list(state.get("warnings", [])),
            }

        # Normal mode.
        seeds = _select_seeds(
            state["initial_results"],
            state["seed_limit"],
        )

        warnings = list(state.get("warnings", []))

        if len(seeds) < state["seed_limit"]:
            warnings.append(
                f"Requested {state['seed_limit']} seeds, but found only "
                f"{len(seeds)} distinct documents in the initial results."
            )

        return {
            "seeds": seeds,
            "seed_ids": [
                seed["passage_id"]
                for seed in seeds
            ],
            "warnings": warnings,
        }
        
    # ---------------------------------------------------------
    # Node 3: search the forward period from one seed
    # ---------------------------------------------------------

    def forward_search_node(
        task: ForwardSearchTask,
    ) -> dict[str, Any]:

        seed = task["seed"]

        outcome = retriever.search_from_passage(
            passage_id=seed["passage_id"],
            representation=task["representation"],
            start_year=task["forward_start_year"],
            end_year=task["forward_end_year"],
            limit=task["transfer_limit"],
            scale=task["forward_scale"],
        )

        return {
            "forward_results": [
                {
                    "seed": seed,
                    "seed_index": task["seed_index"],
                    "outcome": outcome,
                }
            ]
        }

    # ---------------------------------------------------------
    # Dispatch one forward search per seed
    # ---------------------------------------------------------

    def dispatch_forward_searches(
        state: ForwardSearchState,
    ) -> list[Send] | str:

        if not state["seeds"]:
            return "merge_results"

        return [
            Send(
                "forward_search",
                {
                    "seed": seed,
                    "seed_index": index,
                    "representation": state["representation"],
                    "forward_start_year": state["forward_start_year"],
                    "forward_end_year": state["forward_end_year"],
                    "transfer_limit": state["transfer_limit"],
                    "forward_scale": state["forward_scale"],
                },
            )
            for index, seed in enumerate(state["seeds"])
        ]

    # ---------------------------------------------------------
    # Node 4: merge, deduplicate and preserve retrieval edges
    # ---------------------------------------------------------

    def merge_results_node(
        state: ForwardSearchState,
    ) -> dict[str, Any]:

        passages: dict[str, dict[str, Any]] = {}

        for hit in state["initial_results"]:
            passages[hit["passage_id"]] = hit

        warnings = list(state.get("warnings", []))
        edges = []

        for item in sorted(
            state.get("forward_results", []),
            key=lambda item: item["seed_index"],
        ):

            seed = item["seed"]
            outcome = item["outcome"]

            warnings.extend(outcome["warnings"])

            for hit in outcome["results"]:

                target_id = hit["passage_id"]

                passages.setdefault(target_id, hit)

                edges.append({
                    "source_passage_id": seed["passage_id"],
                    "target_passage_id": target_id,
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
                        state["forward_start_year"],
                        state["forward_end_year"],
                    ],
                })

        # First view: remove substantially overlapping windows,
        # independently for each seed.
        deduplicated_edges, suppressed_edges, dedup_warnings = (
            _deduplicate_overlapping_edges(
                edges=edges,
                passages=passages,
                threshold=state["overlap_threshold"],
            )
        )

        warnings.extend(dedup_warnings)

        # Second view: one best remaining passage per document,
        # independently for each seed.
        document_diverse_edges = _select_document_diverse_edges(
            edges=deduplicated_edges,
            passages=passages,
        )

        return {
            "passages": list(passages.values()),

            # All original retrieval relationships.
            "edges": edges,

            # Alternative filtered views.
            "deduplicated_edges": deduplicated_edges,
            "document_diverse_edges": document_diverse_edges,
            "overlap_suppressed_edges": suppressed_edges,

            "warnings": warnings,

            "initial_period": [
                state["initial_start_year"],
                state["initial_end_year"],
            ],

            "forward_period": [
                state["forward_start_year"],
                state["forward_end_year"],
            ],
        }

    # ---------------------------------------------------------
    # Assemble the graph
    # ---------------------------------------------------------

    builder = StateGraph(ForwardSearchState)

    builder.add_node("initial_search", initial_search_node)
    builder.add_node("select_seeds", select_seeds_node)
    builder.add_node("forward_search", forward_search_node)
    builder.add_node("merge_results", merge_results_node)

    builder.add_edge(START, "initial_search")
    builder.add_edge("initial_search", "select_seeds")

    builder.add_conditional_edges(
        "select_seeds",
        dispatch_forward_searches,
        ["forward_search", "merge_results"],
    )

    builder.add_edge("forward_search", "merge_results")
    builder.add_edge("merge_results", END)

    return builder.compile(checkpointer=checkpointer)
