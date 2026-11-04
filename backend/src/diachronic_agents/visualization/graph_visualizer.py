
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from collections import Counter
import textwrap

import networkx as nx
from pyvis.network import Network

from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR


logger = get_logger(__name__)


def _add_graph_title_overlay(
    html_content: str,
    retrieval_graph: dict,
) -> str:
    """Add a fixed, bottom-centred graph title."""

    metadata = retrieval_graph.get("metadata", {})

    query = metadata.get("query", "Diachronic Semantic Search")
    direction = metadata.get("direction", "").capitalize()
    search_range = metadata.get("search_range", {})

    start = search_range.get("start", "?")
    end = search_range.get("end", "?")

    subtitle = (
        f"Diachronic semantic search"
        f" · {direction}"
        f" · {start}–{end}"
    )

    title_html = f"""
    <div id="graph-title-overlay">
        <div class="graph-title"><small style="opacity:50%;font-variant:small-caps">term:</small> “{query}”</div>
        <div class="graph-subtitle">{subtitle}</div>
    </div>

    <style>
        #graph-title-overlay {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 200;
            pointer-events: none;
            text-align: center;
            padding: 12px 24px;
            background: rgba(23, 25, 35, 0.88);
            border-radius: 8px;
            white-space: nowrap;
            font-family: Arial, sans-serif;
        }}

        #graph-title-overlay .graph-title {{
            color: #ffffff;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 5px;
        }}

        #graph-title-overlay .graph-subtitle {{
            color: #cbd5e1;
            font-size: 13px;
        }}
    </style>
    """

    marker = '<div id="mynetwork"'
    position = html_content.find(marker)

    if position == -1:
        raise RuntimeError("Could not find graph container in generated HTML")

    return (
        html_content[:position]
        + title_html
        + html_content[position:]
    )


def _add_generation_boundaries(
    net: Network,
    retrieval_graph: dict,
    graph: nx.DiGraph,
    x_spacing: float,
) -> None:
    """Add vertical lines and labels for period and search boundaries."""

    logger.info("Adding generation boundaries")

    metadata = retrieval_graph.get("metadata", {})
    search_runs = metadata.get("search_runs", [])
    search_range = metadata.get("search_range")

    if not search_range:
        logger.warning("No complete search range in graph metadata")
        return

    years = [
        int(data["pub_year"])
        for _, data in graph.nodes(data=True)
        if data.get("pub_year") is not None
    ]

    if not years:
        logger.warning("No dated nodes; cannot position boundaries")
        return

    min_year = min(years)

    y_positions = [
        float(data.get("y", 0))
        for _, data in graph.nodes(data=True)
    ]

    top_y = min(y_positions) - 100
    bottom_y = max(y_positions) + 100

    # Collect period-transition boundaries.
    boundaries = {}

    for run in sorted(
        search_runs,
        key=lambda item: item.get("generation", 0),
    ):
        period = run.get("target_period")

        if not period:
            continue

        period_start, period_end = map(int, period)
        direction = run.get("direction", "reverse")

        # Only add boundaries for periods containing retrieved passages.
        period_has_passages = any(
            period_start <= year <= period_end
            for year in years
        )

        if not period_has_passages:
            continue

        boundary_year = (
            period_end + 1
            if direction == "reverse"
            else period_start
        )

        boundaries.setdefault(
            boundary_year,
            {
                "year": boundary_year,
                "generation": run.get("generation"),
            },
        )

    # The initial period is always searched. For reverse searches,
    # the earliest boundary is the start of the last period actually reached.
    # For forward searches, the latest boundary is the end of the last
    # period actually reached.

    outer_boundaries = (
        (min(years), int(search_range["end"]) + 1)
        if metadata.get("direction", "reverse") == "reverse"
        else (int(search_range["start"]), max(years) + 1)
    )

    for boundary_year in outer_boundaries:
        boundaries.setdefault(
            boundary_year,
            {
                "year": boundary_year,
                "generation": "endpoint",
            },
        )

    # Draw each unique boundary once.
    for boundary_year, boundary in sorted(boundaries.items()):
        x = (boundary_year - min_year) * x_spacing

        boundary_id = f"generation_boundary_year_{boundary_year}"
        label_id = f"generation_label_year_{boundary_year}"

        # Invisible anchors define the ends of the vertical line.
        net.add_node(
            f"{boundary_id}_top",
            label="",
            x=x,
            y=top_y,
            fixed=True,
            physics=False,
            size=1,
            color={
                "background": "#171923",
                "border": "#171923",
            },
        )

        net.add_node(
            f"{boundary_id}_bottom",
            label="",
            x=x,
            y=bottom_y,
            fixed=True,
            physics=False,
            size=1,
            color={
                "background": "#171923",
                "border": "#171923",
            },
        )

        net.add_edge(
            f"{boundary_id}_top",
            f"{boundary_id}_bottom",
            color={
                "color": "#FFFFFF77",
                "highlight": "#FFFFFFAA",
            },
            width=10,
            dashes=False,
            smooth=False,
            arrows="",
        )

        # Native label is deliberately tiny: the HTML overlay renders it.
        net.add_node(
            label_id,
            label=str(boundary_year),
            x=x,
            y=top_y - 80,
            fixed=True,
            physics=False,
            size=1,
            font={
                "size": 1,
                "color": "#171923",
            },
            color={
                "background": "#171923",
                "border": "#171923",
            },
        )

        logger.info(
            "  Boundary: year=%s generation=%s x=%.1f",
            boundary_year,
            boundary.get("generation"),
            x,
        )

    logger.info(
        "Added %s unique period/search boundaries",
        len(boundaries),
    )


def _assign_chronological_positions(
    graph: nx.DiGraph,
    *,
    x_spacing: float = 2.0,
    y_spacing: float = 80.0,
) -> None:
    """
    Position nodes chronologically from left to right.

    Nodes sharing a publication year are stacked vertically.
    Positions are deterministic for a given graph.
    """

    nodes_by_year: dict[int | None, list[str]] = {}

    for node_id, attributes in graph.nodes(data=True):
        year = attributes.get("pub_year")

        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None

        nodes_by_year.setdefault(year, []).append(node_id)

    known_years = [
        year for year in nodes_by_year
        if year is not None
    ]

    if not known_years:
        min_year = 0
    else:
        min_year = min(known_years)

    # Unknown dates are placed just before the earliest known date.
    unknown_x = -x_spacing

    for year, node_ids in nodes_by_year.items():
        node_ids.sort(
            key=lambda node_id: (
                graph.nodes[node_id].get("title") or "",
                node_id,
            )
        )

        x = (
            unknown_x
            if year is None
            else (year - min_year) * x_spacing
        )

        # Centre each year's nodes around the horizontal axis.
        count = len(node_ids)

        for index, node_id in enumerate(node_ids):
            y = (index - (count - 1) / 2) * y_spacing

            graph.nodes[node_id].update({
                "x": x,
                "y": y,
                "fixed": {
                    "x": True,
                    "y": True,
                },
            })


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
            "weight": 3.0,
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


import re


def _add_html_generation_label_overlay(
    html_content: str,
) -> str:
    """Add zoom-independent HTML labels for generation boundaries."""
    logger.info("Enter _add_html_generation_label_overlay")

    marker = "new vis.Network("
    marker_position = html_content.find(marker)

    if marker_position == -1:
        raise RuntimeError(
            "Could not find 'new vis.Network(' in generated PyVis HTML."
        )

    # Find the assignment immediately preceding the constructor.
    equals_position = html_content.rfind(
        "=",
        0,
        marker_position,
    )

    if equals_position == -1:
        raise RuntimeError(
            "Could not find network variable assignment."
        )

    assignment = html_content[:equals_position].rstrip()

    # Extract the variable name, allowing an optional var/let/const.
    network_variable = assignment.split()[-1]

    # Insert immediately after the constructor statement.
    statement_end = html_content.find(";", marker_position)

    if statement_end == -1:
        raise RuntimeError(
            "Could not find end of PyVis network initialisation."
        )

    insertion_position = statement_end + 1

    script = f"""
    // ------------------------------------------------------------
    // Generation year labels: HTML overlay
    // ------------------------------------------------------------

    const generationNetwork = {network_variable};
    const networkContainer = document.getElementById("mynetwork");

    networkContainer.style.position = "relative";

    const generationLabelLayer = document.createElement("div");

    generationLabelLayer.id = "generation-label-layer";

    Object.assign(generationLabelLayer.style, {{
        position: "absolute",
        top: "0",
        left: "0",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: "100"
    }});

    networkContainer.appendChild(generationLabelLayer);

    const generationLabelNodes = nodes.get().filter(
        node => String(node.id).startsWith("generation_label_")
    );

    const generationLabels = generationLabelNodes.map(node => {{
        const element = document.createElement("div");

        element.textContent = node.label;

        Object.assign(element.style, {{
            position: "absolute",
            width: "4em",
            color: "#ffffff55",
            fontFamily: "Arial, sans-serif",
            fontSize: "20px",
            fontWeight: "bold",
            whiteSpace: "nowrap",
            textAlign: "center",
            textShadow: "0 1px 4px #000000, 0 0 5px #000000",
            transform: "translate(-40%, -50%)",
            display: "none",
            pointerEvents: "none"
        }});

        generationLabelLayer.appendChild(element);

        return {{
            id: node.id,
            element: element
        }};
    }});

    function updateGenerationLabels() {{
        if (!generationLabels.length) return;

        const positions = generationNetwork.getPositions(
            generationLabels.map(item => item.id)
        );

        for (const item of generationLabels) {{
            const position = positions[item.id];

            if (!position) {{
                item.element.style.display = "none";
                continue;
            }}

            const screenPosition =
                generationNetwork.canvasToDOM(position);

            item.element.style.left = `${{screenPosition.x}}px`;
            item.element.style.top = `${{screenPosition.y}}px`;
            item.element.style.display = "block";
        }}
    }}

    generationNetwork.on("zoom", updateGenerationLabels);
    generationNetwork.on("dragging", updateGenerationLabels);
    generationNetwork.on("dragEnd", updateGenerationLabels);
    generationNetwork.on("afterDrawing", updateGenerationLabels);

    requestAnimationFrame(updateGenerationLabels);
    """

    logger.info("Leave _add_html_generation_label_overlay")
    return (
        html_content[:insertion_position]
        + "\n"
        + script
        + html_content[insertion_position:]
    )


def visualise_retrieval_graph(
    retrieval_graph: dict[str, Any],
    output_path: str | Path = OUT_DIR / "graphs" / "retrieval_graph.html",
    height: str = "900px",
    width: str = "100%",
    physics: bool = False,
    layout: str = "chronological",
    x_spacing: float = 20.0,
    y_spacing: float = 300.0,
) -> Path:
    """
    Generate an interactive HTML visualisation of a retrieval graph.

    chronological:
        Publication year determines horizontal position.

    force:
        Use the conventional force-directed network layout.
    """

    if layout not in {"chronological", "force"}:
        raise ValueError("layout must be 'chronological' or 'force'")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_networkx_graph(retrieval_graph)

    if layout == "chronological":
        _assign_chronological_positions(
            graph,
            x_spacing=x_spacing,
            y_spacing=y_spacing,
        )
        y_values = [
            data["y"]
            for _, data in graph.nodes(data=True)
            if data.get("y") is not None
        ]

        logger.info(
            "CHRONOLOGICAL LAYOUT: y_min=%.1f y_max=%.1f y_range=%.1f",
            min(y_values),
            max(y_values),
            max(y_values) - min(y_values),
        )

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

    if layout == "chronological":
        _add_generation_boundaries(
            net,
            retrieval_graph,
            graph,
            x_spacing=x_spacing,
        )
        
    # Node styling.
    for node in net.nodes:
        node_id = node["id"]

        if node_id not in graph:
            continue

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

        if layout == "chronological":
            # Keep the chronological x coordinate fixed.
            # Allow vertical movement only when physics is enabled.
            node["fixed"] = {
                "x": True,
                "y": not physics,
            }

    # Edge styling.
    for edge in net.edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))

        # Generation boundaries are visual elements, not retrieval edges.
        # Preserve the styling assigned when they were created.
        if (
            source.startswith("generation_boundary_")
            and target.startswith("generation_boundary_")
        ):
            continue

        edge["arrows"] = "to"
        edge["width"] = 1
        edge["color"] = {
            "color": "#64748b",
            "highlight": "#cbd5e1",
            "hover": "#cbd5e1",
        }
        
    options = {
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
            "navigationButtons": False,
            "keyboard": True,
            "tooltipDelay": 200,
        },
        "edges": {
            "smooth": {
                "enabled": True,
                "type": "dynamic",
            },
        },
    }

    if layout == "chronological":
        options["layout"] = {
            "improvedLayout": False,
        }

    net.set_options(json.dumps(options))

    html_content = net.generate_html(notebook=False)

    if layout == "chronological":
        html_content = _add_html_generation_label_overlay(html_content)

    html_content = _add_graph_title_overlay(
        html_content,
        retrieval_graph,
    )

    with output_path.open("w", encoding="utf-8") as file:
        file.write(html_content)

    return output_path


