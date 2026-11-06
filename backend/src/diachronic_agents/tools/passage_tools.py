# tools/passage_tools.py
from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import BaseTool, tool

from diachronic_agents.retrieval.passage_retriever import PassageRetriever


Representation = Literal["l8", "last", "mean4"]
Scale = Literal["local", "medium", "broad"]

MAX_RESULTS = 20


def _validate_year_range(start_year: int, end_year: int) -> None:
    if start_year > end_year:
        raise ValueError(
            f"start_year ({start_year}) must not exceed "
            f"end_year ({end_year})"
        )


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(
            f"limit must be between 1 and {MAX_RESULTS}"
        )


def build_passage_tools(
    retriever: PassageRetriever,
) -> list[BaseTool]:
    """Build the investigator's corpus-search tools."""

    @tool
    def semantic_search(
        query: str,
        start_year: int,
        end_year: int,
        representation: Representation = "l8",
        scale: Scale | None = None,
        limit: int = 10,
        include_text: bool = True,
    ) -> dict[str, Any]:
        """Search the historical corpus semantically for a research query.

        Use this to discover passages expressing a concept, idea, or meaning,
        including passages that may not use the query's exact words.

        Supply the publication-year range explicitly. Choose a representation
        and scale appropriate to the search. Results include passage IDs and
        bibliographic and textual information where available.
        """
        _validate_year_range(start_year, end_year)
        _validate_limit(limit)

        return _compact_search_results(retriever.search_text(
            query,
            representation=representation,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            scale=scale,
            include_text=include_text,
        ))

    @tool
    def search_from_passage(
        passage_id: str,
        start_year: int,
        end_year: int,
        representation: Representation = "l8",
        scale: Scale | None = None,
        limit: int = 10,
        include_text: bool = True,
    ) -> dict[str, Any]:
        """Find historically related passages using an existing passage.

        Use this when a retrieved passage provides a useful semantic seed
        for further investigation. The search uses the stored vector for
        that passage, rather than generating a new query embedding.

        The passage ID must identify a passage with a stored vector.
        """
        _validate_year_range(start_year, end_year)
        _validate_limit(limit)

        return _compact_search_results(retriever.search_from_passage(
            passage_id,
            representation=representation,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            scale=scale,
            include_text=include_text,
        ))

    @tool
    def lexical_search(
        query: str,
        start_year: int,
        end_year: int,
        limit: int = 10,
        window_tokens: int = 40,
    ) -> dict[str, Any]:
        """Find exact lexical occurrences of a query in the historical corpus.

        Use this to check whether particular words or phrases occur in a
        period, or to investigate the wording of a concept. Unlike semantic
        search, this requires an exact token sequence.

        Lexical results have no semantic relevance score. Their distance
        field is a placeholder, not a ranking measure.
        """
        _validate_year_range(start_year, end_year)
        _validate_limit(limit)

        if window_tokens < 1:
            raise ValueError("window_tokens must be positive")

        return _compact_search_results(retriever.search_lexical(
            query,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            window_tokens=window_tokens,
        ))

    @tool
    def inspect_passage(
        passage_id: str,
        representation: Representation = "l8",
    ) -> dict[str, Any]:
        """Retrieve the full stored record and text for a passage.

        Use this to examine a passage already discovered by a search.
        This is useful for checking its context and metadata before deciding
        whether it supports a research claim or is a useful seed for another
        search.
        """
        return retriever.inspect_passage(
            passage_id,
            representation=representation,
        )

    return [
        semantic_search,
        search_from_passage,
        lexical_search,
        inspect_passage,
    ]


def _compact_search_results(
    result: dict,
    *,
    excerpt_chars: int = 250,
) -> dict:
    """Return minimal passage records for investigator consumption."""

    return {
        "results": [
            {
                "passage_id": item["passage_id"],
                "pub_year": item.get("pub_year"),
                "rank": item.get("rank"),
                "text": item.get("text", "")[:excerpt_chars],
            }
            for item in result.get("results", [])
            if item.get("passage_id")
        ],
        "warnings": result.get("warnings", []),
    }
    