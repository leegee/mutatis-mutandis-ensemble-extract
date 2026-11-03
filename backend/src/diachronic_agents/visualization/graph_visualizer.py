
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from collections import Counter
import textwrap

import networkx as nx
from pyvis.network import Network

from mutatis_mutandis.lib.corpus_config import OUT_DIR



def report_isolated_nodes(
    retrieval_graph: dict[str, Any],
) -> None:
    graph = build_networkx_graph(retrieval_graph)

    isolated = list(nx.isolates(graph))

    print("\nGRAPH CONNECTIVITY")
    print(f"Total nodes: {graph.number_of_nodes()}")
    print(f"Total edges: {graph.number_of_edges()}")
    print(f"Isolated nodes: {len(isolated)}")

    nodes_by_id = {
        node["id"]: node
        for node in retrieval_graph.get("nodes", [])
    }

    for passage_id in isolated:
        node = nodes_by_id[passage_id]

        print(
            f"{node.get('pub_year', '?')} | "
            f"Seed: {passage_id in retrieval_graph.get('seed_ids', [])} | "
            f"Expanded: {node.get('was_expanded', False)} | "
            f"{node.get('title', 'Untitled')} | "
            f"{passage_id[:12]}"
        )


def build_networkx_graph(
    retrieval_graph: dict[str, Any],
) -> nx.DiGraph:
    """
    Convert a retrieval graph into a directed NetworkX graph.
    """

    graph = nx.DiGraph()

    incoming_sources: dict[str, set[str]] = {}

    for edge in retrieval_graph.get("edges", []):
        incoming_sources.setdefault(edge["target"], set()).add(
            edge["source"]
        )

    convergence_ids = {
        passage_id
        for passage_id, sources in incoming_sources.items()
        if len(sources) > 1
    }

    seed_ids = set(retrieval_graph.get("seed_ids", []))

    # Add passage nodes.
    for node in retrieval_graph.get("nodes", []):
        passage_id = node["id"]

        # Start with the original metadata, avoiding duplicate kwargs.
        attributes = {
            key: value
            for key, value in node.items()
            if key != "id"
        }

        # Set visualisation-specific attributes.
        attributes.update({
            "label": str(node.get("pub_year") or "?"),
            "title": _node_tooltip(node),
            "passage_id": passage_id,
            "is_seed": passage_id in seed_ids,
            "is_convergence": passage_id in convergence_ids,
        })

        graph.add_node(passage_id, **attributes)

    # Add retrieval relationships.
    for edge in retrieval_graph.get("edges", []):
        source = edge["source"]
        target = edge["target"]

        if source not in graph or target not in graph:
            continue

        attributes = {
            key: value
            for key, value in edge.items()
            if key not in {"source", "target"}
        }

        attributes.update({
            "title": _edge_tooltip(edge),
            "weight": 1.0,
        })

        graph.add_edge(source, target, **attributes)

    return graph


def _node_tooltip(node: dict[str, Any]) -> str:
    title = str(node.get("title") or "Untitled")
    author = str(node.get("author") or "Unknown author")
    corpus = str(node.get("corpus") or "")
    passage = str(node.get("text") or "")[:1500]

    width = 65

    return (
        "\n".join(textwrap.wrap(title, width=width))
        + "\n"
        + "─" * width
        + "\n"
        + f"Author: {author}\n"
        + f"Year: {node.get('pub_year', '?')}\n"
        + f"Corpus: {corpus}\n"
        + f"Passage: {node.get('id', '')}\n"
        + "\n"
        + "\n".join(textwrap.wrap(passage, width=width))
    )


def _edge_tooltip(edge: dict[str, Any]) -> str:
    return (
        f"Direction: {edge.get('search_direction', '?')}\n"
        f"Generation: {edge.get('generation', '?')}\n"
        f"Rank: {edge.get('rank', '?')}\n"
        f"Distance: {edge.get('distance', '?')}\n"
        f"Search: {edge.get('search_id', '?')}"
    )    

def visualise_retrieval_graph(
    retrieval_graph: dict[str, Any],
    output_path: str | Path = OUT_DIR / "graphs" / "retrieval_graph.html",
    height: str = "900px",
    width: str = "100%",
    physics: bool = True,
) -> Path:
    """
    Generate an interactive HTML visualisation of a retrieval graph.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_networkx_graph(retrieval_graph)

    net = Network(
        height=height,
        width=width,
        directed=True,
        bgcolor="#171923",
        font_color="#e2e8f0",
        notebook=False,
        cdn_resources="in_line",
    )

    net.from_nx(graph)

    # Node styling.
    for node in net.nodes:
        node_id = node["id"]
        attributes = graph.nodes[node_id]
        discovery_sources = set(
            attributes.get("discovery_sources", [])
        )

        node["shape"] = "dot"
        node["size"] = 18
        node["font"] = {
            "color": "#e2e8f0",
            "size": 16,
        }

        if attributes.get("is_seed"):
            node["color"] = {
                "background": "#e74c3c",
                "border": "#ff8a80",
            }
            node["size"] = 30

        elif attributes.get("is_convergence"):
            node["color"] = {
                "background": "#8e44ad",
                "border": "#c39bd3",
            }
            node["size"] = 25

        elif discovery_sources == {"initial_search"}:
            node["color"] = {
                "background": "#64748b",
                "border": "#94a3b8",
            }

        else:
            node["color"] = {
                "background": "#2980b9",
                "border": "#85c1e9",
            }

    # Edge styling.
    for edge in net.edges:
        edge["arrows"] = "to"
        edge["width"] = 1
        edge["color"] = {
            "color": "#64748b",
            "highlight": "#cbd5e1",
            "hover": "#cbd5e1",
        }

    # Configure physics and interaction.
    physics_enabled = "true" if physics else "false"

    options = json.dumps({
        "physics": {
            "enabled": physics,
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -50,
                "centralGravity": 0.01,
                "springLength": 150,
                "springConstant": 0.08,
                "damping": 0.4,
                "avoidOverlap": 1,
            },
            "minVelocity": 0.75,
            "stabilization": {
                "iterations": 200,
            },
        },
        "interaction": {
            "hover": True,
            "navigationButtons": True,
            "keyboard": True,
            "tooltipDelay": 200,
        },
        "edges": {
            "smooth": {
                "enabled": True,
                "type": "dynamic",
            },
        },
    })

    net.options = json.loads(options)

    # Write interactive HTML.
    html_content = net.generate_html(notebook=False)

    with output_path.open("w", encoding="utf-8") as file:
        file.write(html_content)

    return output_path

