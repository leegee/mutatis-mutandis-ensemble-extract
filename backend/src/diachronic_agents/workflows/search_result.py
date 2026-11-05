from dataclasses import dataclass
from typing import Any


@dataclass
class SearchResult:
    query: str
    direction: str
    initial_period: tuple[int, int]
    target_period: tuple[int, int]
    periods: list[tuple[int, int]]
    results: dict[int, dict]
    graphs: dict[int, dict]
    classifications: dict[int, Any]
    prospects: dict[int, list[dict]]
    cumulative_graph: dict

    def to_dict(self) -> dict:
        """Return a JSON-compatible representation."""

        return {
            "schema_version": 1,
            "query": self.query,
            "direction": self.direction,
            "initial_period": list(self.initial_period),
            "target_period": list(self.target_period),
            "periods": [
                list(period) for period in self.periods
            ],
            "results": {
                str(key): value
                for key, value in self.results.items()
            },
            "graphs": {
                str(key): value
                for key, value in self.graphs.items()
            },
            "classifications": {
                str(key): self._normalise_classification(value)
                for key, value in self.classifications.items()
            },
            "prospects": {
                str(key): value
                for key, value in self.prospects.items()
            },
            "cumulative_graph": self.cumulative_graph,
        }


    @staticmethod
    def _normalise_classification(value: Any) -> dict:
        """Convert a classification result into ordinary dictionaries."""

        if value is None:
            return {"classifications": []}

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")

        if isinstance(value, dict):
            return value

        raise TypeError(
            f"Unsupported classification result type: {type(value).__name__}"
        )


    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        """Reconstruct a SearchResult from its JSON representation."""

        version = data.get("schema_version", 1)

        if version != 1:
            raise ValueError(
                f"Unsupported SearchResult schema version: {version}"
            )

        return cls(
            query=data["query"],
            direction=data["direction"],
            initial_period=tuple(data["initial_period"]),
            target_period=tuple(data["target_period"]),
            periods=[
                tuple(period) for period in data["periods"]
            ],
            results={
                int(key): value
                for key, value in data["results"].items()
            },
            graphs={
                int(key): value
                for key, value in data["graphs"].items()
            },
            classifications={
                int(key): value
                for key, value in data["classifications"].items()
            },
            prospects={
                int(key): value
                for key, value in data["prospects"].items()
            },
            cumulative_graph=data["cumulative_graph"],
        )
