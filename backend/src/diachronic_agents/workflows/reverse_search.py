# diachronic_agents/workflows/reverse_search.py

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.func import entrypoint, task

from diachronic_agents.retrieval.passage_retriever import (
    PassageRetriever,
)


def _validate_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise the workflow's public inputs."""

    required = (
        "query",
        "initial_start_year",
        "initial_end_year",
        "historical_start_year",
        "historical_end_year",
    )

    missing = [
        name for name in required
        if name not in inputs
    ]

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
    values.setdefault(
        "historical_scale",
        values["initial_scale"],
    )
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
        raise ValueError(
            "seed_limit cannot exceed initial_limit"
        )

    return values


def build_reverse_search_workflow(
    retriever: PassageRetriever | None = None,
    *,
    checkpointer=None,
):
    """
    Build a reverse-search workflow.

    A retriever can be injected for testing. In normal use, one
    long-lived PassageRetriever is created for this workflow.
    """

    retriever = retriever or PassageRetriever()
    checkpointer = checkpointer or InMemorySaver()

    @task
    def initial_search(args: dict[str, Any]) -> dict[str, Any]:
        return retriever.search_text(**args)

    @task
    def historical_search(args: dict[str, Any]) -> dict[str, Any]:
        return retriever.search_from_passage(**args)

    @entrypoint(checkpointer=checkpointer)
    def reverse_search(inputs: dict[str, Any]) -> dict[str, Any]:

        params = _validate_inputs(inputs)

        # ---------------------------------------------------------
        # 1. Initial text search
        # ---------------------------------------------------------

        initial = initial_search({
            "query": params["query"],
            "representation": params["representation"],
            "start_year": params["initial_start_year"],
            "end_year": params["initial_end_year"],
            "limit": params["initial_limit"],
            "scale": params["initial_scale"],
        }).result()

        initial_results = initial["results"]
        seeds = initial_results[:params["seed_limit"]]

        # Store unique passages by ID.
        passages: dict[str, dict[str, Any]] = {}

        for hit in initial_results:
            passages[hit["passage_id"]] = hit

        warnings = list(initial["warnings"])
        edges: list[dict[str, Any]] = []

        # ---------------------------------------------------------
        # 2. Historical retrieval from each seed
        # ---------------------------------------------------------

        futures = []

        for seed in seeds:
            futures.append(
                historical_search({
                    "passage_id": seed["passage_id"],
                    "representation": params["representation"],
                    "start_year": params["historical_start_year"],
                    "end_year": params["historical_end_year"],
                    "limit": params["transfer_limit"],
                    "scale": params["historical_scale"],
                })
            )

        # Results are collected in seed order.
        historical_results = [
            future.result()
            for future in futures
        ]

        # ---------------------------------------------------------
        # 3. Record passages and retrieval edges
        # ---------------------------------------------------------

        for seed, outcome in zip(seeds, historical_results):

            warnings.extend(outcome["warnings"])

            for hit in outcome["results"]:

                target_id = hit["passage_id"]

                # A passage is stored once, even if several seeds
                # independently retrieve it.
                passages.setdefault(target_id, hit)

                # But every retrieval relationship is retained.
                edges.append({
                    "source_passage_id": seed["passage_id"],
                    "target_passage_id": target_id,
                    "source_pub_year": seed.get("pub_year"),
                    "target_pub_year": hit.get("pub_year"),
                    "source_scale": seed.get("scale"),
                    "target_scale": hit.get("scale"),
                    "representation": params["representation"],
                    "rank": hit.get("rank"),
                    "distance": hit.get("distance"),
                    "score": hit.get("score"),
                    "source_period": [
                        params["initial_start_year"],
                        params["initial_end_year"],
                    ],
                    "target_period": [
                        params["historical_start_year"],
                        params["historical_end_year"],
                    ],
                })

        # ---------------------------------------------------------
        # 4. Return the complete result
        # ---------------------------------------------------------

        return {
            "query": params["query"],
            "representation": params["representation"],
            "initial_period": [
                params["initial_start_year"],
                params["initial_end_year"],
            ],
            "historical_period": [
                params["historical_start_year"],
                params["historical_end_year"],
            ],
            "initial_scale": params["initial_scale"],
            "historical_scale": params["historical_scale"],
            "seed_ids": [
                seed["passage_id"]
                for seed in seeds
            ],
            "passages": list(passages.values()),
            "edges": edges,
            "warnings": warnings,
        }

    return reverse_search
