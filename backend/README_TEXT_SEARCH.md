# Text search (Postgres)

## Endpoint

`POST /text-search`

```json
{
  "query": "white hair",
  "start_year": 0,
  "end_year": 2030,
  "limit": 30,
  "window_tokens": 40
}
```

Response shape matches `/search` (`SearchResponse` / `Hit`), with optional
`match_start` / `match_end` marking the matched phrase token range.

## Behaviour

1. Tokenise the query (letters / apostrophes, lowercased, length ≥ 2).
2. Find **consecutive** rows in `tokens` matching that phrase (case-insensitive).
3. Expand each hit by `window_tokens` on each side.
4. Join `documents` for title / author / filepath / `pub_year`.
5. Aggregate tokens in the window into `text`.

`passage_id` for these hits is a synthetic sha256 of
`text:{corpus}:{doc_id}:{token_start}:{token_end}` — not a Lance passage id.
“Find similar” / negatives from the semantic UI do not apply.

### Year filter

SQL prefers `documents.pub_year`. If that column is missing, the query is
retried without the year predicate; client-side filtering still applies when
year is present on the row.

## Files

| File | Change |
|------|--------|
| `text_search.py` | **new** — phrase SQL + window expansion |
| `schemas.py` | `TextSearchRequest`; `Hit.match_start/end` |
| `service.py` | `TextSearchParams`, `text_search()` |
| `api.py` | `POST /text-search` |
| `test_api.py` | text-search tests with fake service |

## UI

Hash route `#/text` (nav toggle Semantic | Text). Calls `/text-search`.
Form state is stored separately from the semantic panes in `localStorage`.
