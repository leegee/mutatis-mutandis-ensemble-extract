from mutatis_mutandis.lib.corpus_config import OUT_DIR
from diachronic_agents.workflows.diachronic_task import run_diachronic_search
from diachronic_agents.workflows.graph_task import create_graph
from diachronic_agents.workflows.cvv_task import create_csv


def main() -> None:
    search_result = run_diachronic_search(
        query                = "white hair",
        initial_period       =(0, 1500),
        target_period        = (1501, 2000),
        period_size          = 100,
        first_period_size    = 200,
        representation       = "l8",
        scale                = "broad",
        initial_limit        = 20,
        seed_limit           = 3,
        transfer_limit       = 10,
        expansion_seed_count = 3,
        prospect_limit       = 10,
    )

    graph_path = create_graph(
        search_result,
        output_path = OUT_DIR / "graphs" / "retrieval_graph_forward.html",
    )

    nodes_path, edges_path = create_csv(search_result)

    print(f"Graph: {graph_path}")
    print(f"Nodes: {nodes_path}")
    print(f"Edges: {edges_path}")


if __name__ == "__main__":
    main()
