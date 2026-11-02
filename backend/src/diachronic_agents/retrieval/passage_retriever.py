# diachronic_agents/retrieval/passage_retriever.py

from __future__ import annotations

from pathlib import Path
from typing import Any

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR
from mutatis_mutandis.service import (
    PassageSearchService,
    SearchParams,
)


def _serialise_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """
    Return the fields needed by the workflow.

    Keep checkpoint data small and JSON-serialisable.
    The passage ID remains the stable reference to the full record.
    """
    result = {
        "passage_id": str(hit["passage_id"]),
        "corpus": hit.get("corpus"),
        "doc_id": hit.get("doc_id"),
        "pub_year": (
            int(hit["pub_year"])
            if hit.get("pub_year") is not None
            else None
        ),
        "scale": hit.get("scale"),
        "rank": int(hit["rank"]) if hit.get("rank") is not None else None,
        "distance": (
            float(hit["distance"])
            if hit.get("distance") is not None
            else None
        ),
        "score": (
            float(hit["score"])
            if hit.get("score") is not None
            else None
        ),
        "title": hit.get("title"),
        "author": hit.get("author"),
        "text": hit.get("text"),
        "char_start": hit.get("char_start"),
        "char_end": hit.get("char_end"),
        "word_start": hit.get("word_start"),
        "word_end": hit.get("word_end"),
        "token_start": hit.get("token_start"),
        "token_end": hit.get("token_end"),
        "filepath": hit.get("filepath"),
    }

    return result


class PassageRetriever:
    """
    Adapter around the existing PassageSearchService.

    The service is long-lived and owns its LanceDB connection,
    encoder and vector cache.
    """

    def __init__(
        self,
        service: PassageSearchService | None = None,
        *,
        lance_dir: Path = LANCE_INDEXES_DIR,
    ) -> None:
        self.service = service or PassageSearchService(
            lance_dir,
            application_name="diachronic-agents",
        )

    def _search(
        self,
        *,
        query: str | None = None,
        vector_id: str | None = None,
        representation: str = "l8",
        start_year: int,
        end_year: int,
        limit: int = 10,
        scale: str | None = None,
        include_text: bool = True,
    ) -> dict[str, Any]:

        params = SearchParams(
            query=query,
            vector_id=vector_id,
            representation=representation,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            scale=scale,
            include_text=include_text,
        )

        outcome = self.service.search(params)

        return {
            "results": [
                _serialise_hit(hit)
                for hit in outcome.results
            ],
            "warnings": list(outcome.warnings),
        }

    def search_text(
        self,
        query: str,
        *,
        representation: str = "l8",
        start_year: int,
        end_year: int,
        limit: int = 10,
        scale: str | None = None,
        include_text: bool = True,
    ) -> dict[str, Any]:
        return self._search(
            query=query,
            representation=representation,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            scale=scale,
            include_text=include_text,
        )

    def search_from_passage(
        self,
        passage_id: str,
        *,
        representation: str = "l8",
        start_year: int,
        end_year: int,
        limit: int = 10,
        scale: str | None = None,
        include_text: bool = True,
    ) -> dict[str, Any]:
        return self._search(
            vector_id=passage_id,
            representation=representation,
            start_year=start_year,
            end_year=end_year,
            limit=limit,
            scale=scale,
            include_text=include_text,
        )
