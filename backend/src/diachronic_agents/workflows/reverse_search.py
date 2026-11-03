# diachronic_agents/workflows/reverse_search.py.py

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.types import Send
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from diachronic_agents.retrieval.passage_retriever import PassageRetriever


class HistoricalSearchTask(TypedDict):
    seed: dict[str, Any]
    seed_index: int
    representation: str
    historical_start_year: int
    historical_end_year: int
    transfer_limit: int
    historical_scale: str


class ReverseSearchState(TypedDict, total=False):
    # Inputs
    query: str
    initial_start_year: int
    initial_end_year: int
    historical_start_year: int
    historical_end_year: int
    representation: str
    initial_scale: str
    historical_scale: str
    initial_limit: int
    seed_limit: int
    transfer_limit: int

    # Intermediate results
    initial_results: list[dict[str, Any]]
    seeds: list[dict[str, Any]]
    historical_results: Annotated[
        list[dict[str, Any]],
        operator.add,
    ]
    warnings: list[str]

    # Final output
    seed_ids: list[str]
    passages: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    initial_period: list[int]
    historical_period: list[int]


def _validate_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    required = (
        "query",
        "initial_start_year",
        "initial_end_year",
        "historical_start_year",
        "historical_end_year",
    )

    missing = [name for name in required if name not in inputs]
    if missing:
        raise ValueError(
            f"Missing workflow inputs: {', '.join(missing)}"
        )

    values = dict(inputs)

    for name in (
        "initial_start_year",
        "initial_end_year",
        "historical_start_year",
        "historical_end_year",
    ):
        values[name] = int(values[name])

    if values["initial_start_year"] > values["initial_end_year"]:
        raise ValueError("Invalid initial year interval")

    if values["historical_start_year"] > values["historical_end_year"]:
        raise ValueError("Invalid historical year interval")

    if values["historical_end_year"] >= values["initial_start_year"]:
        raise ValueError(
            "The historical interval must end before "
            "the initial interval begins"
        )

    values["query"] = str(values["query"]).strip()
    if not values["query"]:
        raise ValueError("query cannot be empty")

    values.setdefault("representation", "l8")
    values.setdefault("initial_scale", "broad")
    values.setdefault("historical_scale", values["initial_scale"])
    values.setdefault("initial_limit", 20)
    values.setdefault("seed_limit", 3)
    values.setdefault("transfer_limit", 10)

    values["initial_limit"] = int(values["initial_limit"])
    values["seed_limit"] = int(values["seed_limit"])
    values["transfer_limit"] = int(values["transfer_limit"])

    if values["initial_limit"] < 1:
        raise ValueError("initial_limit must be positive")

    if values["seed_limit"] < 1:
        raise ValueError("seed_limit must be positive")

    if values["transfer_limit"] < 1:
        raise ValueError("transfer_limit must be positive")

    if values["seed_limit"] > values["initial_limit"]:
        raise ValueError("seed_limit cannot exceed initial_limit")

    return values


def _select_seeds(
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Select the highest-ranked passage from each distinct document."""

    selected = []
    seen_documents = set()

    for hit in results:
        doc_id = hit.get("doc_id")

        if doc_id:
            document_key = (hit.get("corpus"), doc_id)
        else:
            document_key = ("passage", hit["passage_id"])

        if document_key in seen_documents:
            continue

        seen_documents.add(document_key)
        selected.append(hit)

        if len(selected) >= limit:
            break

    return selected


def build_reverse_search_workflow(
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
        state: ReverseSearchState,
    ) -> dict[str, Any]:

        params = _validate_inputs(state)

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
        state: ReverseSearchState,
    ) -> dict[str, Any]:

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
    # Node 3: search the historical period from each seed
    # ---------------------------------------------------------

    def historical_search_node(
        task: HistoricalSearchTask,
    ) -> dict[str, Any]:
        seed = task["seed"]

        outcome = retriever.search_from_passage(
            passage_id=seed["passage_id"],
            representation=task["representation"],
            start_year=task["historical_start_year"],
            end_year=task["historical_end_year"],
            limit=task["transfer_limit"],
            scale=task["historical_scale"],
        )

        return {
            "historical_results": [
                {
                    "seed": seed,
                    "seed_index": task["seed_index"],
                    "outcome": outcome,
                }
            ]
        }

    # ---------------------------------------------------------
    # Node 4: merge passages and preserve retrieval edges
    # ---------------------------------------------------------

    def merge_results_node(
        state: ReverseSearchState,
    ) -> dict[str, Any]:

        passages: dict[str, dict[str, Any]] = {}

        for hit in state["initial_results"]:
            passages[hit["passage_id"]] = hit

        warnings = list(state.get("warnings", []))
        edges = []

        for item in sorted(
            state["historical_results"],
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
                        state["historical_start_year"],
                        state["historical_end_year"],
                    ],
                })

        return {
            "passages": list(passages.values()),
            "edges": edges,
            "warnings": warnings,
            "initial_period": [
                state["initial_start_year"],
                state["initial_end_year"],
            ],
            "historical_period": [
                state["historical_start_year"],
                state["historical_end_year"],
            ],
        }

    def dispatch_historical_searches(
        state: ReverseSearchState,
    ) -> list[Send] | str:
        if not state["seeds"]:
            return "merge_results"

        return [
            Send(
                "historical_search",
                {
                    "seed": seed,
                    "seed_index": index,
                    "representation": state["representation"],
                    "historical_start_year": state["historical_start_year"],
                    "historical_end_year": state["historical_end_year"],
                    "transfer_limit": state["transfer_limit"],
                    "historical_scale": state["historical_scale"],
                },
            )
            for index, seed in enumerate(state["seeds"])
        ]

    # ---------------------------------------------------------
    # Assemble the graph
    # ---------------------------------------------------------

    builder = StateGraph(ReverseSearchState)

    builder.add_node("initial_search", initial_search_node)
    builder.add_node("select_seeds", select_seeds_node)
    builder.add_node("historical_search", historical_search_node)
    builder.add_node("merge_results", merge_results_node)

    builder.add_edge(START, "initial_search")
    builder.add_edge("initial_search", "select_seeds")
    builder.add_conditional_edges(
        "select_seeds",
        dispatch_historical_searches,
        ["historical_search", "merge_results"],
    )
    builder.add_edge("historical_search", "merge_results")
    builder.add_edge("merge_results", END)

    return builder.compile(checkpointer=checkpointer)
