
"""
retrieval_graph.py

Build and merge provenance-preserving retrieval graphs from
completed forward and reverse diachronic searches.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping


def _as_passage_list(passages: Any) -> list[dict[str, Any]]:
    """Normalise a workflow passage collection."""
    if isinstance(passages, Mapping):
        return [dict(p) for p in passages.values()]

    return [dict(p) for p in passages]


def _stable_id(prefix: str, payload: Any) -> str:
    """Create a deterministic ID from a serialisable payload."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    digest = hashlib.sha256(encoded).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _edge_identity(edge: Mapping[str, Any]) -> str:
    """
    Identify a retrieval observation.

    The search ID distinguishes separate runs. The remaining fields
    provide a deterministic fallback for older graph data.
    """
    identity = {
        key: value
        for key, value in edge.items()
        if key != "id"
    }

    return _stable_id("retrieval", identity)


def _discovery_sources(
    passage_id: str,
    *,
    seed_ids: set[str],
    retrieved_passage_ids: set[str],
    search_direction: str,
) -> list[str]:
    """
    Identify how a passage entered this search graph.

    Seeds originate in the initial text search. Retrieval targets
    originate in the diachronic search. Unlinked, non-seed passages
    are retained as initial-search results.
    """
    sources = []

    if passage_id in seed_ids or passage_id not in retrieved_passage_ids:
        sources.append("initial_search")

    if passage_id in retrieved_passage_ids:
        sources.append(f"{search_direction}_search")

    return sources


def _convergence(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find target passages retrieved by multiple distinct sources."""
    incoming: dict[str, set[str]] = defaultdict(set)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source and target:
            incoming[target].add(source)

    node_ids = {node["id"] for node in nodes}
    results = []

    for target_id, source_ids in incoming.items():
        if len(source_ids) < 2 or target_id not in node_ids:
            continue

        results.append({
            "target_passage_id": target_id,
            "source_passage_ids": sorted(source_ids),
            "source_count": len(source_ids),
        })

    results.sort(
        key=lambda item: (
            -item["source_count"],
            item["target_passage_id"],
        )
    )

    return results


def build_retrieval_graph(
    result: Mapping[str, Any],
    *,
    search_direction: str,
    generation: int = 0,
    search_id: str | None = None,
) -> dict[str, Any]:
    """
    Build a graph from one completed workflow result.

    Seed nodes belong to `generation`.
    Passages discovered by those seeds belong to `generation + 1`.

    Original retrieval edges are retained, regardless of whether
    their passages were removed from a deduplicated presentation view.
    """
    if search_direction not in {"forward", "reverse"}:
        raise ValueError(
            "search_direction must be 'forward' or 'reverse'"
        )

    if generation < 0:
        raise ValueError("generation cannot be negative")

    passages = _as_passage_list(result.get("passages", []))
    raw_edges = [dict(e) for e in result.get("edges", [])]
    seed_ids = set(result.get("seed_ids", []))

    if search_id is None:
        search_id = _stable_id(
            "search",
            {
                "direction": search_direction,
                "generation": generation,
                "representation": result.get("representation"),
                "initial_period": result.get("initial_period"),
                "target_period": (
                    result.get("forward_period")
                    if search_direction == "forward"
                    else result.get("historical_period")
                ),
                "seed_ids": sorted(seed_ids),
            },
        )

    passages_by_id = {
        passage["passage_id"]: passage
        for passage in passages
        if passage.get("passage_id")
    }

    retrieved_passage_ids = {
        edge["target_passage_id"]
        for edge in raw_edges
        if edge.get("target_passage_id")
    }

    expanded_seed_ids = {
        edge["source_passage_id"]
        for edge in raw_edges
        if edge.get("source_passage_id") in seed_ids
    }

    nodes = []

    for passage_id, passage in passages_by_id.items():
        is_seed = passage_id in seed_ids
        was_expanded = passage_id in expanded_seed_ids

        nodes.append({
            **passage,
            "id": passage_id,
            "generation": generation if is_seed else generation + 1,
            "is_seed": is_seed,
            "was_expanded": was_expanded,
            "seed_generations": (
                [generation] if is_seed else []
            ),
            "expanded_generations": (
                [generation] if was_expanded else []
            ),
            "discovery_sources": _discovery_sources(
                passage_id,
                seed_ids=seed_ids,
                retrieved_passage_ids=retrieved_passage_ids,
                search_direction=search_direction,
            ),
        })

    edges = []

    for raw_edge in raw_edges:
        source_id = raw_edge.get("source_passage_id")
        target_id = raw_edge.get("target_passage_id")

        if not source_id or not target_id:
            continue

        edge = {
            **raw_edge,
            "source": source_id,
            "target": target_id,
            "search_direction": search_direction,
            "search_id": search_id,
            "generation": generation,
        }

        edge["id"] = _edge_identity(edge)
        edges.append(edge)

    convergence = _convergence(nodes, edges)

    target_period = (
        result.get("forward_period")
        if search_direction == "forward"
        else result.get("historical_period")
    )

    search_run = {
        "search_id": search_id,
        "search_direction": search_direction,
        "generation": generation,
        "representation": result.get("representation"),
        "initial_period": result.get("initial_period"),
        "target_period": target_period,
        "seed_ids": sorted(seed_ids),
    }

    return {
        "metadata": {
            "search_direction": search_direction,
            "representation": result.get("representation"),
            "initial_period": result.get("initial_period"),
            "target_period": target_period,
            "search_runs": [search_run],
            "node_count": len(nodes),
            "edge_count": len(edges),
            "convergence_count": len(convergence),
        },
        "nodes": nodes,
        "edges": edges,
        "seed_ids": sorted(seed_ids),
        "expanded_seed_ids": sorted(expanded_seed_ids),
        "unexpanded_seed_ids": sorted(seed_ids - expanded_seed_ids),
        "convergence": convergence,
    }



def merge_retrieval_graphs(
    existing_graph: Mapping[str, Any],
    new_graph: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Merge retrieval graphs into a cumulative provenance-preserving graph.

    Nodes are merged by passage ID.
    Edges are merged by stable retrieval identity.
    Earliest discovery generations are preserved.
    Discovery sources, seed history and expansion history are accumulated.
    """

    nodes_by_id: dict[str, dict[str, Any]] = {}
    edges_by_id: dict[str, dict[str, Any]] = {}

    # ---------------------------------------------------------
    # Merge nodes and edges from both graphs
    # ---------------------------------------------------------

    for graph in (existing_graph, new_graph):

        graph_edges = graph.get("edges", [])

        # Recover incoming search directions for older graph nodes
        # which may not yet have discovery_sources.
        incoming_directions: dict[str, set[str]] = defaultdict(set)

        for original_edge in graph_edges:
            edge = dict(original_edge)

            target = (
                edge.get("target")
                or edge.get("target_passage_id")
            )
            direction = edge.get("search_direction")

            if target and direction in {"forward", "reverse"}:
                incoming_directions[target].add(
                    f"{direction}_search"
                )

        # -----------------------------------------------------
        # Nodes
        # -----------------------------------------------------

        for original in graph.get("nodes", []):

            node = dict(original)
            node_id = node.get("id") or node.get("passage_id")

            if not node_id:
                continue

            node["id"] = node_id

            node.setdefault(
                "generation",
                0 if node.get("is_seed") else 1,
            )
            node.setdefault("is_seed", False)
            node.setdefault("was_expanded", False)

            node.setdefault(
                "seed_generations",
                [node["generation"]] if node["is_seed"] else [],
            )
            node.setdefault(
                "expanded_generations",
                (
                    [node["generation"]]
                    if node["was_expanded"]
                    else []
                ),
            )

            # Recover provenance for older graphs.
            if "discovery_sources" not in node:
                sources = set(
                    incoming_directions.get(node_id, set())
                )

                if node["is_seed"] or not sources:
                    sources.add("initial_search")

                node["discovery_sources"] = sorted(sources)

            else:
                node["discovery_sources"] = sorted(
                    set(node["discovery_sources"])
                )

            if node_id not in nodes_by_id:
                nodes_by_id[node_id] = node
                continue

            previous = nodes_by_id[node_id]

            # Preserve existing passage data, filling missing values.
            for key, value in node.items():
                if key not in previous or previous[key] is None:
                    previous[key] = value

            # Accumulate discovery provenance.
            previous["discovery_sources"] = sorted(
                set(previous.get("discovery_sources", []))
                | set(node.get("discovery_sources", []))
            )

            # Keep the earliest discovery generation.
            previous["generation"] = min(
                previous["generation"],
                node["generation"],
            )

            previous["is_seed"] = (
                previous["is_seed"] or node["is_seed"]
            )
            previous["was_expanded"] = (
                previous["was_expanded"] or node["was_expanded"]
            )

            previous["seed_generations"] = sorted(
                set(previous["seed_generations"])
                | set(node["seed_generations"])
            )

            previous["expanded_generations"] = sorted(
                set(previous["expanded_generations"])
                | set(node["expanded_generations"])
            )

        # -----------------------------------------------------
        # Edges
        # -----------------------------------------------------

        for original_edge in graph_edges:

            edge = dict(original_edge)

            source = (
                edge.get("source")
                or edge.get("source_passage_id")
            )
            target = (
                edge.get("target")
                or edge.get("target_passage_id")
            )

            if not source or not target:
                continue

            edge["source"] = source
            edge["target"] = target

            # Retain existing stable IDs, or create one for older edges.
            edge_id = edge.get("id") or _edge_identity(edge)
            edge["id"] = edge_id

            if edge_id not in edges_by_id:
                edges_by_id[edge_id] = edge
                continue

            # Preserve existing edge data, filling missing values.
            previous = edges_by_id[edge_id]

            for key, value in edge.items():
                if key not in previous or previous[key] is None:
                    previous[key] = value

    # ---------------------------------------------------------
    # Finalise nodes and edges
    # ---------------------------------------------------------

    nodes = sorted(
        nodes_by_id.values(),
        key=lambda node: (
            node["generation"],
            node.get("pub_year") or 0,
            node["id"],
        ),
    )

    edges = sorted(
        edges_by_id.values(),
        key=lambda edge: (
            edge.get("generation", 0),
            edge["source"],
            edge["target"],
            edge["id"],
        ),
    )

    # ---------------------------------------------------------
    # Recalculate graph-level relationships
    # ---------------------------------------------------------

    seed_ids = sorted(
        node["id"]
        for node in nodes
        if node.get("is_seed")
    )

    expanded_seed_ids = sorted(
        node["id"]
        for node in nodes
        if node.get("was_expanded")
    )

    convergence = _convergence(nodes, edges)

    # ---------------------------------------------------------
    # Merge search-run metadata
    # ---------------------------------------------------------

    search_runs = []
    seen_search_ids = set()

    for graph in (existing_graph, new_graph):
        for run in graph.get("metadata", {}).get("search_runs", []):

            search_id = run.get("search_id")

            if search_id and search_id not in seen_search_ids:
                seen_search_ids.add(search_id)
                search_runs.append(dict(run))

    metadata = {
        "search_runs": search_runs,
        "search_count": len(search_runs),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "seed_count": len(seed_ids),
        "expanded_seed_count": len(expanded_seed_ids),
        "convergence_count": len(convergence),
    }

    return {
        "metadata": metadata,
        "nodes": nodes,
        "edges": edges,
        "seed_ids": seed_ids,
        "expanded_seed_ids": expanded_seed_ids,
        "unexpanded_seed_ids": sorted(
            set(seed_ids) - set(expanded_seed_ids)
        ),
        "convergence": convergence,
    }

