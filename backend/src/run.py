
from diachronic_agents.workflows.reverse_search import (
    build_reverse_search_workflow,
)
from diachronic_agents.workflows.diachronic_task import (
    run_diachronic_search,
)


def main() -> None:
    workflow = build_reverse_search_workflow()

    result = run_diachronic_search(
        query="white hair",

        # Initial query period
        initial_period=(1900, 2000),

        # Search backwards from 1899 to 0
        target_period=(0, 1899),

        # Successive 100-year windows
        period_size=100,

        representation="l8",
        scale="broad",

        initial_limit=20,
        seed_limit=3,
        transfer_limit=10,
        expansion_seed_count=3,
        prospect_limit=10,

        workflow=workflow,

        output_path="graphs/retrieval_graph_reverse.html",
    )

    graph = result["cumulative_graph"]

    print(
        f"Completed {len(result['results'])} periods: "
        f"{len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges"
    )


if __name__ == "__main__":
    main()
