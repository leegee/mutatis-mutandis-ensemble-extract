"""
mutatis_mutandis/api.py

FastAPI application.

Run (from the repo root, one worker: each worker loads its own MacBERTh copy):

    uvicorn mutatis_mutandis.api:app --app-dir src --port 8000

Environment:
    PASSAGE_SEARCH_WARMUP        "1" (default) loads the encoder at startup
    PASSAGE_SEARCH_CORS_ORIGINS  comma-separated origins to allow (optional)

The single-file web UI in ./static is served at /ui/ (and / redirects there).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR
from mutatis_mutandis.lib.macberth import PASSAGE_REPRESENTATIONS

from mutatis_mutandis.core import VectorNotFoundError
from mutatis_mutandis.schemas import (
    SearchRequest,
    SearchResponse,
    TextSearchRequest,
)
from mutatis_mutandis.service import (
    PassageSearchService,
    SearchParams,
    TextSearchParams,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = PassageSearchService(LANCE_INDEXES_DIR, application_name="passage-search-api")
    if os.getenv("PASSAGE_SEARCH_WARMUP", "1") == "1":
        service.warmup()
    app.state.search_service = service
    yield


app = FastAPI(
    title="Passage Search API",
    description="Semantic passage search over MacBERTh embeddings (LanceDB + Postgres).",
    version="1.1.0",
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.getenv("PASSAGE_SEARCH_CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# FRONTEND_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"


def get_service(request: Request) -> PassageSearchService:
    return request.app.state.search_service


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/representations")
def representations():
    return {"representations": list(PASSAGE_REPRESENTATIONS)}


# Plain `def` on purpose: LanceDB, Postgres and the encoder are blocking,
# so FastAPI runs this in its threadpool instead of stalling the event loop.
@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest, service: PassageSearchService = Depends(get_service)):
    params = SearchParams(
        query=req.query,
        vector_id=req.vector_id,
        negative_ids=tuple(req.negative_ids),
        representation=req.representation,
        start_year=req.start_year,
        end_year=req.end_year,
        limit=req.limit,
        beta=req.beta,
        overfetch=req.overfetch,
        include_text=req.include_text,
    )
    try:
        outcome = service.search(params)
    except VectorNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return SearchResponse(
        count=len(outcome.results),
        results=outcome.results,
        warnings=outcome.warnings,
    )


@app.post("/text-search", response_model=SearchResponse)
def text_search(req: TextSearchRequest, service: PassageSearchService = Depends(get_service)):
    """Keyword / phrase search over Postgres tokens (no embeddings)."""
    params = TextSearchParams(
        query=req.query,
        start_year=req.start_year,
        end_year=req.end_year,
        limit=req.limit,
        window_tokens=req.window_tokens,
    )
    try:
        outcome = service.text_search(params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return SearchResponse(
        count=len(outcome.results),
        results=outcome.results,
        warnings=outcome.warnings,
    )


# --- Web UI -----------------------------------------------------------------
# Same origin as the API, so the page needs no CORS configuration.
if FRONTEND_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/ui/")
