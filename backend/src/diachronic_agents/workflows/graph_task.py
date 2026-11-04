
from pathlib import Path

from diachronic_agents.workflows.diachronic_task import SearchResult
from diachronic_agents.visualization.graph_visualizer import (
    visualise_retrieval_graph,
)
from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_logging import get_logger


logger = get_logger(__name__)


def create_graph(
    search_result: SearchResult,
    *,
    output_path: str | Path | None = None,
    height: str = "900px",
    width: str = "100%",
    physics: bool = False,
    layout: str = "chronological",
    x_spacing: float = 20.0,
    y_spacing: float = 300.0,
) -> Path:
    """
    Create an HTML visualisation of a completed diachronic search.
    """

    if not isinstance(search_result, SearchResult):
        raise TypeError(
            "search_result must be a SearchResult instance"
        )

    retrieval_graph = search_result.cumulative_graph

    if not retrieval_graph:
        raise ValueError(
            "SearchResult contains no cumulative retrieval graph"
        )

    if output_path is None:
        output_path = (
            OUT_DIR
            / "graphs"
            / f"retrieval_graph_{search_result.direction}.html"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Creating retrieval graph")
    logger.info("Query: %s", search_result.query)
    logger.info("Direction: %s", search_result.direction)
    logger.info(
        "Nodes: %d | Edges: %d",
        len(retrieval_graph["nodes"]),
        len(retrieval_graph["edges"]),
    )
    logger.info("Output: %s", output_path)

    graph_path = visualise_retrieval_graph(
        retrieval_graph,
        output_path=output_path,
        height=height,
        width=width,
        physics=physics,
        layout=layout,
        x_spacing=x_spacing,
        y_spacing=y_spacing,
    )

    logger.info("Graph created: %s", graph_path)

    return graph_path
