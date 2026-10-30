"""
mutatis_mutandis/schemas.py

Pydantic request/response models for the HTTP API.
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from mutatis_mutandis.lib.macberth import PASSAGE_REPRESENTATIONS

from mutatis_mutandis.lib.corpus_config import PASSAGE_SCALES

# passage_ids in this corpus are 64-char lowercase hex (sha256). Loosen the
# pattern here if you ever introduce other ID formats.
PassageId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Optional[str] = Field(None, min_length=1, max_length=2000)
    vector_id: Optional[PassageId] = None
    negative_ids: List[PassageId] = Field(default_factory=list, max_length=50)
    representation: str = "l8"
    start_year: int = Field(0, ge=0, le=2030)
    end_year: int = Field(2030, ge=0, le=2030)
    limit: int = Field(1000, ge=1, le=1000)
    beta: float = Field(0.5, ge=0.0, le=5.0)
    overfetch: int = Field(5, ge=1, le=20)
    include_text: bool = True
    scale: Optional[str] = Field(
        None,
        description="Restrict to one scale: " + ", ".join(PASSAGE_SCALES),
    )

    @field_validator("scale")
    @classmethod
    def _known_scale(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PASSAGE_SCALES:
            raise ValueError(f"scale must be one of {PASSAGE_SCALES}")
        return v

    @field_validator("representation")
    @classmethod
    def _known_representation(cls, v: str) -> str:
        if v not in PASSAGE_REPRESENTATIONS:
            raise ValueError(f"representation must be one of {list(PASSAGE_REPRESENTATIONS)}")
        return v

    @model_validator(mode="after")
    def _check(self):
        if bool(self.query) == bool(self.vector_id):
            raise ValueError("provide exactly one of query or vector_id")
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


class TextSearchRequest(BaseModel):
    """Keyword / phrase search over Postgres tokens (not embeddings)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500)
    start_year: int = Field(0, ge=0, le=2030)
    end_year: int = Field(2030, ge=0, le=2030)
    limit: int = Field(1000, ge=1, le=1000)
    window_tokens: int = Field(
        40,
        ge=5,
        le=200,
        description="Tokens of context on each side of the matched phrase.",
    )

    @model_validator(mode="after")
    def _check(self):
        if self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        return self


class Hit(BaseModel):
    rank: int
    passage_id: str
    corpus: str
    doc_id: str
    pub_year: int
    scale: Optional[str] = None          # PASSAGE_SCALES "local" | "medium" | "broad"  
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    distance: float
    score: Optional[float] = None
    sim_q: Optional[float] = None
    sim_neg: Optional[float] = None
    word_start: Optional[int] = None
    word_end: Optional[int] = None
    token_start: int
    token_end: int
    title: Optional[str] = None
    author: Optional[str] = None
    filepath: Optional[str] = None
    text: Optional[str] = None
    # Present on text-search hits: token range of the matched phrase itself.
    match_start: Optional[int] = None
    match_end: Optional[int] = None


class SearchResponse(BaseModel):
    count: int
    results: List[Hit]
    warnings: List[str] = Field(default_factory=list)
