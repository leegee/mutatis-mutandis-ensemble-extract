from mutatis_mutandis.lib.corpus_config import OUT_DIR
from diachronic_agents.workflows.diachronic_task import run_diachronic_search


def main() -> None:
    result = run_diachronic_search(
        query="white hair",
        initial_period=(0, 1500),
        target_period=(1501, 2000),

        # Reproduce the original 200-year first window,
        # followed by 100-year windows.
        period_size=100,
        first_period_size=200,

        representation="l8",
        scale="broad",

        initial_limit=20,
        seed_limit=3,
        transfer_limit=10,
        expansion_seed_count=3,
        prospect_limit=10,
        output_path=OUT_DIR / "graphs" / "retrieval_graph_forward.html",
    )

    graph = result["cumulative_graph"]

    print(
        f"Completed {len(result['results'])} periods: "
        f"{len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges"
    )


if __name__ == "__main__":
    main()
