# workflows/eploration/graph_explorer.py

from __future__ import annotations

from typing import Any, Literal

from diachronic_agents.workflows.search_result import SearchResult


Direction = Literal["incoming", "outgoing", "both"]


def _get_graph(search_result: SearchResult) -> dict[str, Any]:
    graph = search_result.cumulative_graph

    if not isinstance(graph, dict):
        raise TypeError("SearchResult.cumulative_graph must be a dictionary")

    return graph


def _get_nodes_by_id(
    search_result: SearchResult,
) -> dict[str, dict[str, Any]]:
    graph = _get_graph(search_result)

    return {
        node.get("passage_id", node.get("id")): node
        for node in graph.get("nodes", [])
        if node.get("passage_id", node.get("id")) is not None
    }


def get_graph_metadata(
    search_result: SearchResult,
) -> dict[str, Any]:
    """Return cumulative graph metadata."""
    return _get_graph(search_result).get("metadata", {})


def get_node(
    search_result: SearchResult,
    passage_id: str,
) -> dict[str, Any] | None:
    """Return a passage node by its passage ID."""
    return _get_nodes_by_id(search_result).get(passage_id)


def get_connected_edges(
    search_result: SearchResult,
    passage_id: str,
    direction: Direction = "both",
) -> list[dict[str, Any]]:
    """Return edges connected to a passage.

    Direction:
        outgoing: passage is the source
        incoming: passage is the target
        both: either endpoint
    """
    if direction not in ("incoming", "outgoing", "both"):
        raise ValueError(f"Unsupported direction: {direction}")

    graph = _get_graph(search_result)
    edges = graph.get("edges", [])

    connected = []

    for edge in edges:
        is_outgoing = edge.get("source_passage_id") == passage_id
        is_incoming = edge.get("target_passage_id") == passage_id

        if direction == "outgoing" and is_outgoing:
            connected.append(edge)
        elif direction == "incoming" and is_incoming:
            connected.append(edge)
        elif direction == "both" and (is_outgoing or is_incoming):
            connected.append(edge)

    return connected


def get_neighbours(
    search_result: SearchResult,
    passage_id: str,
    direction: Direction = "both",
) -> list[dict[str, Any]]:
    """Return neighbouring passages with the edge connecting each one.

    Each item contains:
        node: the neighbouring passage
        edge: the retrieval edge
        direction: incoming or outgoing relative to passage_id
    """
    nodes_by_id = _get_nodes_by_id(search_result)
    edges = get_connected_edges(search_result, passage_id, direction)

    neighbours = []

    for edge in edges:
        source_id = edge.get("source_passage_id")
        target_id = edge.get("target_passage_id")

        if source_id == passage_id:
            neighbour_id = target_id
            edge_direction = "outgoing"
        else:
            neighbour_id = source_id
            edge_direction = "incoming"

        node = nodes_by_id.get(neighbour_id)

        if node is None:
            continue

        neighbours.append({
            "node": node,
            "edge": edge,
            "direction": edge_direction,
        })

    return neighbours


def get_nodes_by_generation(
    search_result: SearchResult,
    generation: int,
) -> list[dict[str, Any]]:
    """Return all nodes discovered in a given generation."""
    graph = _get_graph(search_result)

    return [
        node
        for node in graph.get("nodes", [])
        if node.get("generation") == generation
    ]


def get_nodes_by_period(
    search_result: SearchResult,
    start_year: int,
    end_year: int,
) -> list[dict[str, Any]]:
    """Return nodes whose publication year falls within an inclusive range."""
    if start_year > end_year:
        raise ValueError("start_year must not be later than end_year")

    graph = _get_graph(search_result)

    return [
        node
        for node in graph.get("nodes", [])
        if isinstance(node.get("pub_year"), int)
        and start_year <= node["pub_year"] <= end_year
    ]


def get_seeds(
    search_result: SearchResult,
    generation: int | None = None,
) -> list[dict[str, Any]]:
    """Return seed nodes, optionally restricted to a generation."""
    graph = _get_graph(search_result)

    return [
        node
        for node in graph.get("nodes", [])
        if node.get("is_seed") is True
        and (
            generation is None
            or generation in node.get("seed_generations", [])
        )
    ]


def get_expanded_seeds(
    search_result: SearchResult,
    generation: int | None = None,
) -> list[dict[str, Any]]:
    """Return nodes that were expanded as seeds."""
    graph = _get_graph(search_result)

    return [
        node
        for node in graph.get("nodes", [])
        if node.get("was_expanded") is True
        and (
            generation is None
            or generation in node.get("expanded_generations", [])
        )
    ]


def get_search_runs(
    search_result: SearchResult,
) -> list[dict[str, Any]]:
    """Return the individual searches that contributed to the graph."""
    metadata = get_graph_metadata(search_result)

    return sorted(
        metadata.get("search_runs", []),
        key=lambda run: run.get("generation", -1),
    )


def get_discovery_history(
    search_result: SearchResult,
    passage_id: str,
) -> dict[str, Any] | None:
    """Return the recorded discovery and expansion history for a passage.

    Also identifies search runs in which the passage was a seed, and
    runs represented by edges connected to the passage.
    """
    node = get_node(search_result, passage_id)

    if node is None:
        return None

    search_runs = get_search_runs(search_result)

    seed_runs = [
        run
        for run in search_runs
        if passage_id in run.get("seed_ids", [])
    ]

    connected_edges = get_connected_edges(
        search_result,
        passage_id,
    )

    connected_search_ids = {
        edge.get("search_id")
        for edge in connected_edges
        if edge.get("search_id") is not None
    }

    connected_runs = [
        run
        for run in search_runs
        if run.get("search_id") in connected_search_ids
    ]

    return {
        "passage_id": passage_id,
        "discovery_sources": node.get("discovery_sources", []),
        "seed_generations": node.get("seed_generations", []),
        "expanded_generations": node.get("expanded_generations", []),
        "seed_runs": seed_runs,
        "connected_runs": connected_runs,
    }


def get_convergence_points(
    search_result: SearchResult,
    target_passage_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return convergence records, optionally for one target passage."""
    graph = _get_graph(search_result)
    convergence = graph.get("convergence", [])

    if target_passage_id is None:
        return convergence

    return [
        item
        for item in convergence
        if item.get("target_passage_id") == target_passage_id
    ]
    