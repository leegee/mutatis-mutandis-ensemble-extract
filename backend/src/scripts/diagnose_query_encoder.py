#!/usr/bin/env python3
"""
scripts/diagnose_query_encoder.py

Diagnostic only. Compares two MacBERTh query encoders against the existing
LanceDB passage index:

  existing  : mutatis_mutandis.lib.macberth.encode_passage_query()
              (word-split, no special tokens, per-word then per-query mean)
  alternative: whole query as a normal string, special tokens attended,
              masked mean pooling identical to the indexing pipeline.

Nothing is modified: no model, index, vectors, encoder or application code.

Run from the backend directory:
    python scripts/diagnose_query_encoder.py

Retrieval uses the project's search_passages() and fetch_passage_texts()
(signatures verified against the supplied source). --skip-retrieval runs the
encoder comparison only, without importing any database module.

# Encoder comparison only (no DB imports)
python scripts/diagnose_query_encoder.py --skip-retrieval

# Full run
python scripts/diagnose_query_encoder.py --representation l8 --scale broad --limit 10

"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, OUT_DIR

# --- make `mutatis_mutandis` importable regardless of cwd -------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402

DEFAULT_QUERIES = ["noah", "asdfasdfasdf", "white hair", "white-haired", "albino"]
REPRESENTATIONS = ("l8", "last", "mean4")
MAX_MODEL_TOKENS = 512
TEXT_DISPLAY_CHARS = 400


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

def pool_hidden(hidden, attention_mask):
    """Exact copy of the indexing pipeline's masked mean pooling."""
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    summed = (hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1)
    return summed / counts


def select_hidden(hidden_states, representation):
    if representation == "l8":
        return hidden_states[8]
    if representation == "last":
        return hidden_states[-1]
    if representation == "mean4":
        return torch.stack(hidden_states[-4:], dim=0).mean(dim=0)
    raise ValueError(f"Unknown representation {representation!r}")


@torch.inference_mode()
def encode_alternative(text, representation, macberth):
    """Passage-style query encoder (short queries only, no chunking)."""
    encoded = macberth.tokenizer(
        [text],
        padding=True,
        truncation=False,
        return_tensors="pt",
    )
    n_attended = int(encoded["attention_mask"].sum())
    if n_attended > MAX_MODEL_TOKENS:
        raise ValueError(
            f"Query has {n_attended} attended tokens (> {MAX_MODEL_TOKENS}); "
            "the alternative encoder does not chunk. Shorten the query."
        )

    input_ids = encoded["input_ids"].to(macberth.device)
    attention_mask = encoded["attention_mask"].to(macberth.device)

    output = macberth.encode(
        input_ids=input_ids,
        attention_mask=attention_mask,
        output_hidden_states=True,
    )
    hidden = select_hidden(output.hidden_states, representation)
    pooled = pool_hidden(hidden, attention_mask)

    vector = pooled[0].float().cpu().numpy().astype(np.float32)
    ids = input_ids[0].cpu().tolist()
    return vector, {
        "token_ids": ids,
        "tokens": macberth.tokenizer.convert_ids_to_tokens(ids),
        "n_attended": n_attended,
    }


def existing_tokenisation(text, macberth):
    words = text.split()
    enc = macberth.tokenizer(
        words,
        is_split_into_words=True,
        add_special_tokens=False,
        truncation=False,
    )
    ids = list(enc["input_ids"])
    return {
        "words": words,
        "token_ids": ids,
        "tokens": macberth.tokenizer.convert_ids_to_tokens(ids),
    }


def vector_stats(v):
    return {
        "dim": int(v.shape[0]),
        "norm": float(np.linalg.norm(v)),
        "all_finite": bool(np.isfinite(v).all()),
    }


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ---------------------------------------------------------------------------
# Retrieval (exact project APIs, verified against the supplied source)
#
#   search_passages(db, query_vector, representation, start_year, end_year,
#                   limit, include_vectors=False, negative_vectors=None,
#                   beta=0.5, overfetch=5, scale=None) -> list[dict]
#       rows carry: passage_id, corpus, doc_id, pub_year, scale, char_start,
#       char_end, token_start, token_end, distance (cosine), table
#   fetch_passage_texts(conn, rows) -> list[dict], same order as rows, keys
#       title, author, filepath, passage_text (all None if no match)
#   get_connection(*, connect_timeout=5, application_name="corpus") -> psycopg
#       Connection, used as a context manager exactly as service.py does.
# ---------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, Path):
        return str(x)
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x

def make_retriever(args):
    # Imported lazily: corpus_db raises at import time unless CORPUS_PGDATABASE /
    # PGDATABASE and CORPUS_PGPASSWORD / PGPASSWORD are set in the environment.
    try:
        from mutatis_mutandis.core import normalise_vector, search_passages
        from mutatis_mutandis.lib.corpus_db import get_connection
        from mutatis_mutandis.service import PassageSearchService
        from mutatis_mutandis.texts import fetch_passage_texts
    except RuntimeError as exc:
        raise SystemExit(
            f"Cannot import database modules: {exc}\n"
            "Set the same PG* / CORPUS_PG* environment variables the app uses, "
            "or run with --skip-retrieval."
        )

    # Instantiating the service only opens the LanceDB connection (no encoder).
    service = PassageSearchService(args.lance_dir, application_name="diagnose-query-encoder")
    db = service._db

    def retrieve(vector):
        rows = search_passages(
            db=db,
            query_vector=normalise_vector(vector, "Query vector"),
            representation=args.representation,
            start_year=args.start_year,
            end_year=args.end_year,
            limit=args.limit,
            include_vectors=False,
            negative_vectors=None,      # disabled for this experiment
            beta=args.beta,             # unused without negatives
            overfetch=args.overfetch,   # unused without negatives
            scale=args.scale,
        )
        metas = []
        if rows:
            with get_connection(application_name="diagnose-query-encoder") as conn:
                metas = fetch_passage_texts(conn, rows)
        out = []
        for rank, (row, meta) in enumerate(zip(rows, metas), 1):
            out.append({
                "rank": rank,
                "cosine_distance": float(row["distance"]),
                "year": row.get("pub_year"),
                "corpus": row.get("corpus"),
                "doc_id": row.get("doc_id"),
                "passage_id": row.get("passage_id"),
                "scale": row.get("scale"),
                "table": row.get("table"),
                "title": meta.get("title"),
                "author": meta.get("author"),
                "text": meta.get("passage_text"),
            })
        return out

    return retrieve


def print_results(label, rows):
    print(f"\n  --- {label} ---")
    if not rows:
        print("  (no results)")
    for r in rows:
        text = (r["text"] or "").replace("\n", " ")
        if len(text) > TEXT_DISPLAY_CHARS:
            text = text[:TEXT_DISPLAY_CHARS] + "…"
        print(f"  #{r['rank']:<2} dist={r['cosine_distance']:.6f}  year={r['year']}  "
              f"corpus={r['corpus']}  doc={r['doc_id']}  passage={r['passage_id']}")
        print(f"      title : {r['title']}")
        print(f"      author: {r['author']}")
        print(f"      text  : {text}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lance-dir", default=LANCE_INDEXES_DIR)
    p.add_argument("--queries", nargs="*", default=None)
    p.add_argument("--representation", choices=REPRESENTATIONS, default="l8")
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--scale", choices=("local", "medium", "broad"), default="broad")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--beta", type=float, default=0.5)
    p.add_argument("--overfetch", type=int, default=5)
    p.add_argument("--json-out", default=OUT_DIR / 'diagnostic.json')
    p.add_argument("--skip-retrieval", action="store_true",
                   help="only compare encoders; do not open the database")
    return p.parse_args()


def main():
    args = parse_args()
    from mutatis_mutandis.lib.macberth import _get_macberth, encode_passage_query

    queries = args.queries if args.queries else DEFAULT_QUERIES
    macberth = _get_macberth()
    print(f"Model device: {macberth.device}; representation: {args.representation}")
    print(f"Model dtype : {next(macberth.model.parameters()).dtype} "
          "(indexing on CUDA used fp16; stored vectors are float16)")

    retrieve = None if args.skip_retrieval else make_retriever(args)
    report = {"settings": {k: v for k, v in vars(args).items() if k != "json_out"}, "queries": []}

    for q in queries:
        print("\n" + "=" * 100)
        print(f"QUERY: {q!r}")
        print("=" * 100)

        ex_vec = np.asarray(
            encode_passage_query(q, args.representation, macberth), dtype=np.float32)
        alt_vec, alt_tok = encode_alternative(q, args.representation, macberth)
        ex_tok = existing_tokenisation(q, macberth)

        print("\nA. Tokenisation")
        print(f"  existing words      : {ex_tok['words']}")
        print(f"  existing content ids: {ex_tok['token_ids']}  {ex_tok['tokens']}")
        print(f"  alternative full ids: {alt_tok['token_ids']}  {alt_tok['tokens']}")
        print(f"  alternative attended: {alt_tok['n_attended']}")
        same_content = alt_tok["token_ids"][1:-1] == ex_tok["token_ids"]
        print(f"  content tokens identical (alt minus CLS/SEP vs existing): {same_content}")

        s_ex, s_alt = vector_stats(ex_vec), vector_stats(alt_vec)
        cos = cosine(ex_vec, alt_vec)
        print("\nB. Vectors")
        print(f"  existing   : {s_ex}")
        print(f"  alternative: {s_alt}")
        print(f"  cosine(existing, alternative) = {cos:.6f}")

        entry = {
            "query": q,
            "tokenisation": {"existing": ex_tok, "alternative": alt_tok,
                             "content_tokens_identical": same_content},
            "vectors": {"existing": s_ex, "alternative": s_alt, "cosine_existing_vs_alternative": cos},
            "retrieval": {},
        }

        if retrieve is not None:
            print("\nC. Retrieval (identical parameters; vectors L2-normalised in retrieve())")
            for key, label, vec in (("existing", "EXISTING encoder", ex_vec),
                                    ("alternative", "ALTERNATIVE encoder", alt_vec)):
                rows = retrieve(vec)
                print_results(label, rows)
                entry["retrieval"][key] = rows
                if rows:
                    ds = [r["cosine_distance"] for r in rows]
                    print(f"  best/mean distance: {min(ds):.6f} / {sum(ds)/len(ds):.6f}")
            ex_ids = [r["passage_id"] for r in entry["retrieval"]["existing"]]
            alt_ids = [r["passage_id"] for r in entry["retrieval"]["alternative"]]
            overlap = len(set(ex_ids) & set(alt_ids))
            print(f"\n  top-{args.limit} passage overlap between encoders: {overlap}/{args.limit}")
            entry["retrieval"]["overlap"] = overlap
        report["queries"].append(entry)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(_jsonable(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
