# experiments/explore_graph.py

from diachronic_agents.persistence.search_result_store import (
    load_search_result,
)
from diachronic_agents.workflows.exploration.graph_explorer import (
    get_graph_metadata,
    get_node,
    get_neighbours,
    get_discovery_history,
    get_convergence_points,
)

search_result = load_search_result(r"D:\src\mutatis-mutandis-ensemble-extract\out\search_results\20261105T114418Z_forward_white-hair_fb7b5513_0-1500_to_1501-2000_5b912df8.json")

print(get_graph_metadata(search_result))

node = get_node(search_result, "4e9e54c5adc00dce5a07edec47a4c1cb745bcb00f5809e19c1bd78b5b6a5b24d")
print(node)

print(get_neighbours(search_result, "4e9e54c5adc00dce5a07edec47a4c1cb745bcb00f5809e19c1bd78b5b6a5b24d"))
print(get_discovery_history(search_result, "4e9e54c5adc00dce5a07edec47a4c1cb745bcb00f5809e19c1bd78b5b6a5b24d"))
print(get_convergence_points(search_result))