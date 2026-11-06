from mutatis_mutandis.lib.corpus_config import OUT_DIR
from diachronic_agents.workflows.diachronic_task import run_diachronic_search
from diachronic_agents.workflows.graph_task import create_graph
from diachronic_agents.workflows.cvv_task import create_csv
from diachronic_agents.persistence.search_result_store import (
    archive_search_result,
    list_search_results,
    load_search_result,
)
from diachronic_agents.classification_configs import CLASSIFICATION_CONFIG

def main() -> None:
    search_result = run_diachronic_search(
        query                 = "white hair",
        initial_period        =(0, 1500),
        target_period         = (1501, 2000),
        period_size           = 100,
        first_period_size     = 200,
        representation        = "l8",
        scale                 = "broad",
        initial_limit         = 20,
        seed_limit            = 3,
        transfer_limit        = 10,
        expansion_seed_count  = 3,
        prospect_limit        = 10,
        config                = CLASSIFICATION_CONFIG,
    )

    graph_path = create_graph(
        search_result,
        output_path = OUT_DIR / "graphs" / "retrieval_graph_forward.html",
    )

    nodes_path, edges_path = create_csv(search_result)

    print(f"Graph: {graph_path}")
    print(f"Nodes: {nodes_path}")
    print(f"Edges: {edges_path}")

    archive_dir = OUT_DIR / "search_results"

    archive_path = archive_search_result(
        search_result,
        archive_dir,
    )

    print(f"Archive: {archive_path}")

    loaded = load_search_result(archive_path)

    # print(loaded.query)
    # print(loaded.cumulative_graph)
    # archive_path.unlink()


if __name__ == "__main__":
    main()
