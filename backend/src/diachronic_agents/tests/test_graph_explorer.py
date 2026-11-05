from diachronic_agents.workflows.exploration.graph_explorer import (
    get_connected_edges,
    get_convergence_points,
    get_discovery_history,
    get_expanded_seeds,
    get_graph_metadata,
    get_neighbours,
    get_node,
    get_nodes_by_generation,
    get_nodes_by_period,
    get_search_runs,
    get_seeds,
)


def test_get_node(sample_search_result):
    node = get_node(sample_search_result, "passage-001")

    assert node is not None
    assert node["passage_id"] == "passage-001"
    assert node["feature_type"] == "human_hair"


def test_get_node_missing(sample_search_result):
    assert get_node(sample_search_result, "missing") is None


def test_get_connected_edges_outgoing(sample_search_result):
    edges = get_connected_edges(
        sample_search_result,
        "passage-001",
        direction="outgoing",
    )

    assert len(edges) == 1
    assert edges[0]["target_passage_id"] == "passage-003"


def test_get_connected_edges_incoming(sample_search_result):
    edges = get_connected_edges(
        sample_search_result,
        "passage-001",
        direction="incoming",
    )

    assert len(edges) == 1
    assert edges[0]["source_passage_id"] == "passage-002"


def test_get_expanded_seeds(sample_search_result):
    seeds = get_expanded_seeds(sample_search_result)

    assert {
        node["passage_id"]
        for node in seeds
    } == {"passage-001", "passage-002"}



def test_get_nodes_by_generation(sample_search_result):
    nodes = get_nodes_by_generation(sample_search_result, 1)

    assert {
        node["passage_id"]
        for node in nodes
    } == {"passage-001", "passage-003"}



def test_get_nodes_by_period(sample_search_result):
    nodes = get_nodes_by_period(
        sample_search_result,
        1800,
        1899,
    )

    assert {
        node["passage_id"]
        for node in nodes
    } == {"passage-001"}

    
def test_get_seeds(sample_search_result):
    seeds = get_seeds(sample_search_result)

    assert {
        node["passage_id"]
        for node in seeds
    } == {"passage-001", "passage-002"}


def test_get_expanded_seeds(sample_search_result):
    seeds = get_expanded_seeds(sample_search_result)

    assert {
        node["passage_id"]
        for node in seeds
    } == {"passage-001", "passage-002"}


def test_get_search_runs(sample_search_result):
    runs = get_search_runs(sample_search_result)

    assert len(runs) == 2
    assert runs[0]["generation"] == 0
    assert runs[1]["generation"] == 1


def test_get_discovery_history(sample_search_result):
    history = get_discovery_history(
        sample_search_result,
        "passage-001",
    )

    assert history is not None
    assert history["seed_generations"] == [1]
    assert history["expanded_generations"] == [1]
    assert len(history["seed_runs"]) == 1
    assert len(history["connected_runs"]) == 2


def test_get_graph_metadata(sample_search_result):
    metadata = get_graph_metadata(sample_search_result)

    assert metadata["search_count"] == 2


def test_get_convergence_points(sample_search_result):
    assert get_convergence_points(sample_search_result) == []