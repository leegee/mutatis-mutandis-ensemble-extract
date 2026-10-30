## Ingestion

See the main project's Tier 0.

    CREATE TABLE documents (
      corpus TEXT NOT NULL,
      doc_id TEXT NOT NULL,
      filepath TEXT NOT NULL,
      title TEXT,
      author TEXT,
      pub_year INTEGER,
      publisher TEXT,
      pub_place TEXT,
      source_date_raw TEXT,
      token_count INTEGER,
      lang CHAR(3) NOT NULL DEFAULT 'eng',
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP GENERATED ALWAYS AS (CURRENT_TIMESTAMP) STORED, -- from pg v12
      PRIMARY KEY (corpus, doc_id)
    );

    CREATE TABLE tokens (
      corpus TEXT NOT NULL,
      doc_id TEXT NOT NULL,
      token_idx INTEGER NOT NULL,
      token TEXT NOT NULL,
      raw_token text,
      canonical TEXT,
      PRIMARY KEY (corpus, doc_id, token_idx),
      FOREIGN KEY (corpus, doc_id)
          REFERENCES documents(corpus, doc_id)
          ON DELETE CASCADE
    );

The `ingest` directory contains cost-conscious scripts for reading the above database (available on request) to produce token Parquet shards placed  on Google Drive for the standalone Google Colab script (`ingest/colab_embed_passages.py`) which creates into passage-level MacBERTh embeddings, without requiring PostgreSQL or LanceDB. It generates 768-dimensional vectors using layer 8, the final layer, and the mean of the final four layers, dividing text into 40-word windows with a 20-word hop (50% overlap) while preserving document metadata and original token offsets. Per-document checkpoints, validation, and atomic publication support safe resumption after interruptions. As it is stand-alone, configuration should remain synchronised with lib.corpus_config and lib.macberth, one of the many comporises made in unfunded research. A further script adds those shards to the Lance database reading for searching.

Different window sizes and embedding methods are tried in the main project (`mutatis-mutandis`) where the above configuration has proven for the task at hand.

## Semantic Search Engine Layout

| File                          | Role                                                                                           |
|-------------------------------|------------------------------------------------------------------------------------------------|
| `ingest/`                     | As above |
| `static/`                     | Small Solid JS app providing a search interface to the Lance and PG databases |
| `core.py`                     | Retrieval primitives: normalise, table selection, stored vectors, search + negative re-ranking |
| `texts.py`                    | Batched Postgres lookup (one query for all hits) |
| `service.py`                  | `PassageSearchService` + `SearchParams`: shared by CLI and API |
| `schemas.py`                  | Pydantic request/response models |
| `api.py`                      | FastAPI app |
| `cli.py`                      | Command-line front end |
| `static/index.html`           | Single-file web UI (SolidJS, no build step), served at `/ui/` |
| `passages_search.py`          | Optional shim so old `ps.search_passages` imports keep working |
| `../lib/macberth-huggingface` | A copy of the MacBERTh model from Hugging Face |

## Search UI

  cd backend
  uv sync
  uv run uvicorn mutatis_mutandis.api:app --app-dir src --port 8000 --reload --reload-dir src

  http://localhost:8000/
  http://localhost:8000/docs

Use one worker as each worker process loads its own copy of the model.

## Examples

    curl -X POST localhost:8000/search -H 'content-type: application/json' \
      -d '{"query": "white hair", "representation": "l8", "limit": 20}'

    curl -X POST localhost:8000/search -H 'content-type: application/json' \
      -d '{"query": "white hair",
           "negative_ids": ["dfbee39870fbbababa5fc24da247fb8468a82350bca1170209458b84568be2c3"],
           "beta": 0.6, "overfetch": 5}'

    # ids only, skip Postgres entirely
    curl -X POST localhost:8000/search -H 'content-type: application/json' \
      -d '{"vector_id": "ef2f4aaf...", "include_text": false}'

## Status codes

200 ok · 404 unknown `vector_id` · 422 invalid request (or ambiguous vector)

Skipped negatives are reported in the `warnings` array of a 200 response.

## Tests

    pytest ./src/mutatis_mutandis/*test*

## Solid UI

`static/index.html` is one file: SolidJS is loaded from jsDelivr through a pinned
import map, so there is nothing to build. For offline use, download the four
`solid-js` files named in the import map into `static/vendor/` and point the map
at `/ui/vendor/...`.

URL options: `?panes=2` (up to 6) enables the multi-pane layout and an
"+ Add query" button; `?api=http://host:8000` points the page at another origin
(that server then needs `PASSAGE_SEARCH_CORS_ORIGINS`).

Form state (queries, settings, excluded passages) is kept in `localStorage`;
results are not.

Code layout inside the page: one store holding an array of panes; actions that take
a pane id; components that read their pane by id. Cross-pane features are memos
over the store (see `docIndex` / `overlaps`).
