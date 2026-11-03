"""
mutatis_mutandis/service.py

Application layer shared by the CLI and the HTTP API. Owns the LanceDB
connection, the (thread-safe) query encoder, and a small cache of stored
passage vectors. Knows nothing about argparse, FastAPI or Pydantic.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import lancedb

from mutatis_mutandis.lib.corpus_config import PASSAGE_SCALES
from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.macberth import encode_passage_query
from mutatis_mutandis.years import current_year

from mutatis_mutandis.core import (
    load_passage_vector,
    normalise_vector,
    search_passages,
)
from mutatis_mutandis.texts import fetch_passage_texts
from mutatis_mutandis.text_search import search_text_passages

logger = get_logger("mutatis.service")


@dataclass(frozen=True)
class SearchParams:
    query: Optional[str] = None
    vector_id: Optional[str] = None
    negative_ids: Tuple[str, ...] = ()
    representation: str = "l8"
    start_year: int = 0
    end_year: int = field(default_factory=current_year)
    limit: int = 30
    beta: float = 0.5
    overfetch: int = 5
    include_text: bool = True
    scale: Optional[str] = None   # None = all scales

    def __post_init__(self):
        if bool(self.query) == bool(self.vector_id):
            raise ValueError("provide exactly one of query or vector_id")
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.overfetch < 1:
            raise ValueError("overfetch must be >= 1")
        if self.scale is not None and self.scale not in PASSAGE_SCALES:
            raise ValueError(f"scale must be one of {list(PASSAGE_SCALES)}")


@dataclass(frozen=True)
class TextSearchParams:
    query: str
    start_year: int = 0
    end_year: int = field(default_factory=current_year)
    limit: int = 30
    window_tokens: int = 40

    def __post_init__(self):
        if not (self.query or "").strip():
            raise ValueError("query must be non-empty")
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.window_tokens < 1:
            raise ValueError("window_tokens must be >= 1")


@dataclass
class SearchOutcome:
    results: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PassageSearchService:
    def __init__(
        self,
        lance_dir,
        *,
        vector_cache_size: int = 256,
        application_name: str = "passage-search",
    ):
        self.lance_dir = Path(lance_dir)
        self.application_name = application_name
        self._db = lancedb.connect(str(self.lance_dir))
        # The encoder may sit on a GPU / non-thread-safe tokenizer.
        self._encode_lock = threading.Lock()
        # Stored vectors are immutable, and finding one scans every table.
        self._load_vector = lru_cache(maxsize=vector_cache_size)(
            self._load_vector_uncached
        )
        logger.info("Lance directory: %s", self.lance_dir)

    # -- internals ---------------------------------------------------------

    def _load_vector_uncached(self, passage_id: str, representation: str):
        return load_passage_vector(self._db, passage_id, representation)

    def _encode(self, text: str, representation: str):
        with self._encode_lock:
            raw = encode_passage_query(text, representation)
        return normalise_vector(raw, "Text query")

    def _query_vector(self, params: SearchParams):
        if params.vector_id:
            return self._load_vector(params.vector_id, params.representation)
        return self._encode(params.query, params.representation)

    @staticmethod
    def _to_hit(rank: int, row: dict, meta: Optional[dict]) -> dict:
        meta = meta or {}
        return {
            "rank": rank,
            "passage_id": row["passage_id"],
            "corpus": row["corpus"],
            "doc_id": row["doc_id"],
            "pub_year": row["pub_year"],
            "scale": row.get("scale"),
            "char_start": row.get("char_start"),
            "char_end": row.get("char_end"),
            "distance": row["distance"],
            "score": row.get("score"),
            "sim_q": row.get("sim_q"),
            "sim_neg": row.get("sim_neg"),
            "word_start": row.get("word_start"),
            "word_end": row.get("word_end"),
            "token_start": row["token_start"],
            "token_end": row["token_end"],
            "title": meta.get("title"),
            "author": meta.get("author"),
            "filepath": meta.get("filepath"),
            "text": meta.get("passage_text"),
        }

    @staticmethod
    def _to_text_hit(rank: int, row: dict) -> dict:
        """Map a text_search row (already includes metadata) to API hit shape."""
        return {
            "rank": rank,
            "passage_id": row["passage_id"],
            "corpus": row["corpus"],
            "doc_id": row["doc_id"],
            "pub_year": row.get("pub_year") or 0,
            "distance": float(row.get("distance") or 0.0),
            "score": row.get("score"),
            "sim_q": row.get("sim_q"),
            "sim_neg": row.get("sim_neg"),
            "word_start": row.get("word_start"),
            "word_end": row.get("word_end"),
            "token_start": row["token_start"],
            "token_end": row["token_end"],
            "title": row.get("title"),
            "author": row.get("author"),
            "filepath": row.get("filepath"),
            "text": row.get("text"),
            "match_start": row.get("match_start"),
            "match_end": row.get("match_end"),
        }

    # -- public API --------------------------------------------------------

    def warmup(self, representation: str = "l8") -> None:
        """Load the encoder (and any lazy state) before serving traffic."""
        self._encode("warmup", representation)
        logger.info("Encoder warm (%s)", representation)

    def search(self, params: SearchParams) -> SearchOutcome:
        t0 = time.perf_counter()
        warnings: List[str] = []

        query_vector = self._query_vector(params)

        negatives = []
        for nid in params.negative_ids:
            try:
                negatives.append(self._load_vector(nid, params.representation))
            except ValueError as e:
                warnings.append(f"Skipped negative {nid}: {e}")
        if params.negative_ids and not negatives:
            warnings.append(
                "No valid negative vectors loaded; results are not re-ranked"
            )

        rows = search_passages(
            db=self._db,
            query_vector=query_vector,
            representation=params.representation,
            start_year=params.start_year,
            end_year=params.end_year,
            limit=params.limit,
            include_vectors=False,
            negative_vectors=negatives or None,
            beta=params.beta,
            overfetch=params.overfetch,
            scale=params.scale,
        )

        metas: List[Optional[dict]] = [None] * len(rows)
        if rows and params.include_text:
            with get_connection(application_name=self.application_name) as conn:
                metas = fetch_passage_texts(conn, rows)

        hits = [
            self._to_hit(rank, row, meta)
            for rank, (row, meta) in enumerate(zip(rows, metas), start=1)
        ]

        logger.info(
            "search done: %d hits in %.0f ms (rep=%s scale=%s years=%s-%s negatives=%d)",
            len(hits),
            (time.perf_counter() - t0) * 1000,
            params.representation,
            params.scale or "all",
            params.start_year,
            params.end_year,
            len(negatives),
        )
        return SearchOutcome(results=hits, warnings=warnings)

    def text_search(self, params: TextSearchParams) -> SearchOutcome:
        """Postgres phrase search over tokens; does not use Lance or the encoder."""
        t0 = time.perf_counter()
        with get_connection(application_name=self.application_name) as conn:
            rows = search_text_passages(
                conn,
                params.query,
                limit=params.limit,
                start_year=params.start_year,
                end_year=params.end_year,
                window_tokens=params.window_tokens,
            )
        hits = [self._to_text_hit(rank, row) for rank, row in enumerate(rows, start=1)]
        logger.info(
            "text_search done: %d hits in %.0f ms (years=%s-%s window=%d)",
            len(hits),
            (time.perf_counter() - t0) * 1000,
            params.start_year,
            params.end_year,
            params.window_tokens,
        )
        return SearchOutcome(results=hits, warnings=[])
