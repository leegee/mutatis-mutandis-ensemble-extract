#!/usr/bin/env python3
"""
scripts/diagnose_query_space.py

Read-only diagnostic of the geometry of the passage index, to explain why a
nonsense query (asdfasdfasdf) can score better cosine distances than a
meaningful one (noah). Nothing is modified or written except the JSON report.

Experiments
-----------
1. Per-query baselines. Draw a random sample of stored passage vectors and,
   for each query, measure the distribution of cosine similarity between the
   query and that sample (mean, std, percentiles). The top-k hits are then
   reported as z-scores against the query's OWN baseline, so queries can be
   compared fairly even if their raw distances are not comparable.
2. Corpus centroid. How anisotropic is the sample (mean resultant length,
   average pairwise cosine), and how close is each query to the centroid?
3. Hubness. Probe the full index with many stored passages (or with words
   from --probe-words) and count how often each passage / document appears in
   the top-k of OTHER documents. The hits of each diagnostic query are then
   cross-referenced against those counts.

Retrieval (query hits and hubness probes) uses production search by default.
Use --exact to bypass the approximate vector index: the exactness diagnostic
showed production search misses most true top-10 hits for short text queries,
which distorts the hit z-scores and the hubness cross-reference.

Run from the backend directory:

    python scripts/diagnose_query_space.py --exact
    python scripts/diagnose_query_space.py
    python scripts/diagnose_query_space.py --encoder both --sample-size 10000 --probes 500
    python scripts/diagnose_query_space.py --skip-queries           # no model needed
    python scripts/diagnose_query_space.py --with-text              # hub text via Postgres

Only LanceDB is needed unless --with-text is given (then the same PG* /
CORPUS_PG* environment variables as the app are required).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# --- make `mutatis_mutandis` (and the sibling script) importable -------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import numpy as np  # noqa: E402

from exact_search import get_search_fn  # noqa: E402

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, OUT_DIR  # noqa: E402

DEFAULT_QUERIES = ["noah", "asdfasdfasdf", "white hair", "white-haired", "albino"]
REPRESENTATIONS = ("l8", "last", "mean4")
ID_CHUNK = 500  # passage ids per `IN (...)` lookup


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def unit_rows(m):
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    if (norms < 1e-12).any():
        raise ValueError("zero-length vector in input")
    return m / norms


def unit(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / np.linalg.norm(v)


def describe(x):
    x = np.asarray(x, dtype=np.float64)
    p = np.percentile(x, [1, 50, 90, 99])
    return {
        "mean": float(x.mean()), "std": float(x.std()),
        "p01": float(p[0]), "p50": float(p[1]), "p90": float(p[2]), "p99": float(p[3]),
        "max": float(x.max()),
    }


def gini(counts):
    x = np.sort(np.asarray(counts, dtype=np.float64))
    if x.size == 0 or x.sum() == 0:
        return 0.0
    n = x.size
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def where_clause(args):
    return (f"pub_year >= {int(args.start_year)} AND pub_year <= {int(args.end_year)} "
            f"AND scale = '{args.scale}'")


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


# ---------------------------------------------------------------------------
# Sampling stored vectors (uses only LanceDB calls that core.py also uses,
# plus Table.count_rows; checked against lancedb 0.41)
# ---------------------------------------------------------------------------

def sample_stored(db, args, rng):
    from mutatis_mutandis.core import candidate_tables

    where = where_clause(args)
    tables = candidate_tables(db, args.representation, args.start_year, args.end_year)
    if not tables:
        raise SystemExit(f"No tables for representation={args.representation!r} "
                         f"in {args.start_year}-{args.end_year}")

    handles = {name: db.open_table(name) for name in tables}
    counts = {name: handles[name].count_rows(where) for name in tables}
    total = sum(counts.values())
    if total == 0:
        raise SystemExit(f"No rows match: {where}")
    print(f"Index: {len(tables)} table(s), {total:,} '{args.scale}' passages in range")

    n_target = min(args.sample_size, total)
    probs = np.array([counts[t] for t in tables], dtype=np.float64) / total
    allocation = rng.multinomial(n_target, probs)

    cols = ["passage_id", "corpus", "doc_id", "pub_year", "token_start", "token_end", "vector"]
    vectors, meta = [], []
    for name, n_t in zip(tables, allocation):
        n_t = int(min(n_t, counts[name]))
        if n_t == 0:
            continue
        tbl = handles[name]
        ids = (tbl.search().where(where).select(["passage_id"])
               .limit(counts[name]).to_arrow().column("passage_id").to_pylist())
        chosen = rng.choice(len(ids), size=min(n_t, len(ids)), replace=False)
        chosen_ids = [ids[i] for i in chosen]

        for i in range(0, len(chosen_ids), ID_CHUNK):
            part = chosen_ids[i:i + ID_CHUNK]
            in_list = ",".join("'" + p.replace("'", "''") + "'" for p in part)
            arrow = (tbl.search().where(f"passage_id IN ({in_list})")
                     .select(cols).limit(len(part) * 2).to_arrow())
            col = arrow.column("vector").combine_chunks()
            dim = col.type.list_size
            vectors.append(col.values.to_numpy(zero_copy_only=False)
                           .reshape(-1, dim).astype(np.float32))
            for row in arrow.drop_columns(["vector"]).to_pylist():
                row["table"] = name
                meta.append(row)
        print(f"  sampled {n_t:>6,} from {name}")

    V = np.concatenate(vectors, axis=0)
    assert V.shape[0] == len(meta)
    return V, meta, total


# ---------------------------------------------------------------------------
# Query encoding (reuses the encoders from diagnose_query_encoder.py)
# ---------------------------------------------------------------------------

def encode_queries(queries, args):
    from diagnose_query_encoder import encode_alternative  # sibling script
    from mutatis_mutandis.lib.macberth import _get_macberth, encode_passage_query

    macberth = _get_macberth()
    out = {}
    for q in queries:
        if args.encoder in ("existing", "both"):
            out[(q, "existing")] = np.asarray(
                encode_passage_query(q, args.representation, macberth), dtype=np.float32)
        if args.encoder in ("alternative", "both"):
            out[(q, "alternative")] = encode_alternative(q, args.representation, macberth)[0]
    return out


# ---------------------------------------------------------------------------
# Experiments 1 & 2
# ---------------------------------------------------------------------------

def corpus_geometry(V):
    n = V.shape[0]
    mu = V.mean(axis=0)
    resultant = float(np.linalg.norm(mu))
    centroid = unit(mu)
    to_centroid = V @ centroid
    return {
        "sample_size": int(n),
        "mean_resultant_length": resultant,
        # mean pairwise cosine between distinct sample vectors
        "mean_pairwise_cosine": float((n * resultant ** 2 - 1.0) / (n - 1)),
        "cosine_to_centroid": describe(to_centroid),
    }, centroid, to_centroid


def query_baseline(q_unit, V, centroid, to_centroid, db, args):
    search_passages = get_search_fn(args.exact)

    sims = V @ q_unit
    base = describe(sims)
    q_centroid = float(q_unit @ centroid)

    rows = search_passages(
        db=db, query_vector=q_unit, representation=args.representation,
        start_year=args.start_year, end_year=args.end_year, limit=args.limit,
        include_vectors=False, negative_vectors=None, scale=args.scale,
    )
    top_sims = np.array([1.0 - float(r["distance"]) for r in rows])
    std = base["std"] if base["std"] > 0 else 1.0
    z = (top_sims - base["mean"]) / std if top_sims.size else top_sims

    return {
        "baseline_similarity": base,
        "query_cosine_to_centroid": q_centroid,
        "centroid_cosine_percentile_in_sample": float((to_centroid < q_centroid).mean() * 100),
        "top_similarity": top_sims.tolist(),
        "top1_similarity": float(top_sims[0]) if top_sims.size else None,
        "top1_z": float(z[0]) if z.size else None,
        "topk_mean_z": float(z.mean()) if z.size else None,
        "top1_minus_p99": float(top_sims[0] - base["p99"]) if top_sims.size else None,
        "hits": [{"passage_id": r["passage_id"], "doc_id": r["doc_id"],
                  "pub_year": r["pub_year"], "distance": float(r["distance"])} for r in rows],
    }


# ---------------------------------------------------------------------------
# Experiment 3: hubness
# ---------------------------------------------------------------------------

def run_probes(db, args, rng, V, meta, probe_vectors):
    """probe_vectors: list of (label, unit vector, doc_id or None, passage_id or None)."""
    search_passages = get_search_fn(args.exact)

    passage_hits, doc_hits, row_by_pid = Counter(), Counter(), {}
    shortfall = 0
    fetch = max(args.probe_fetch, args.probe_k * 3)

    for n, (label, vec, own_doc, own_pid) in enumerate(probe_vectors, 1):
        rows = search_passages(
            db=db, query_vector=vec, representation=args.representation,
            start_year=args.start_year, end_year=args.end_year, limit=fetch,
            include_vectors=False, negative_vectors=None, scale=args.scale,
        )
        kept = [r for r in rows
                if r["passage_id"] != own_pid and (own_doc is None or r["doc_id"] != own_doc)]
        kept = kept[:args.probe_k]
        if len(kept) < args.probe_k:
            shortfall += 1
        for r in kept:
            passage_hits[r["passage_id"]] += 1
            doc_hits[(r["corpus"], r["doc_id"])] += 1
            row_by_pid.setdefault(r["passage_id"], r)
        if n % 100 == 0:
            print(f"  probed {n}/{len(probe_vectors)}")
    return passage_hits, doc_hits, row_by_pid, shortfall


def build_probes(args, rng, V, meta):
    if args.probe_words:
        words = [w.strip() for w in Path(args.probe_words).read_text(encoding="utf-8").splitlines()
                 if w.strip()]
        if len(words) > args.probes:
            words = [words[i] for i in rng.choice(len(words), size=args.probes, replace=False)]
        # always the alternative (passage-style) encoder for probes
        saved, args.encoder = args.encoder, "alternative"
        enc = encode_queries(words, args)
        args.encoder = saved
        return [(w, unit(enc[(w, "alternative")]), None, None) for w in words], "words"
    n = min(args.probes, V.shape[0])
    idx = rng.choice(V.shape[0], size=n, replace=False)
    return [(meta[i]["passage_id"], unit(V[i]), meta[i]["doc_id"], meta[i]["passage_id"])
            for i in idx], "stored passages (same-document hits excluded)"


def hub_report(passage_hits, doc_hits, n_probes, k, shortfall):
    slots = sum(passage_hits.values())
    counts = np.array(list(passage_hits.values()), dtype=np.float64)
    top10 = sum(c for _, c in passage_hits.most_common(10))
    top_docs = doc_hits.most_common(10)
    return {
        "probes": n_probes, "k": k,
        "probes_with_fewer_than_k_hits": shortfall,
        "result_slots": int(slots),
        "distinct_passages_retrieved": int(len(passage_hits)),
        "distinct_documents_retrieved": int(len(doc_hits)),
        "gini_of_passage_counts": gini(counts),
        "share_of_slots_top10_passages": float(top10 / slots) if slots else 0.0,
        "share_of_slots_top10_documents": float(sum(c for _, c in top_docs) / slots) if slots else 0.0,
    }


def attach_text(hub_rows, rows_by_pid):
    """Optional: pull titles/text for hub passages from Postgres."""
    try:
        from mutatis_mutandis.lib.corpus_db import get_connection
        from mutatis_mutandis.texts import fetch_passage_texts
    except RuntimeError as exc:
        raise SystemExit(f"Cannot import database modules: {exc}\n"
                         "Set the PG* / CORPUS_PG* environment variables or drop --with-text.")
    rows = [rows_by_pid[h["passage_id"]] for h in hub_rows]
    with get_connection(application_name="diagnose-query-space") as conn:
        metas = fetch_passage_texts(conn, rows)
    for h, m in zip(hub_rows, metas):
        h["title"], h["text"] = m.get("title"), m.get("passage_text")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lance-dir", default=LANCE_INDEXES_DIR)
    p.add_argument("--queries", nargs="*", default=None)
    p.add_argument("--encoder", choices=("alternative", "existing", "both"), default="alternative")
    p.add_argument("--representation", choices=REPRESENTATIONS, default="l8")
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--scale", choices=("local", "medium", "broad"), default="broad")
    p.add_argument("--limit", type=int, default=10, help="top-k for the query hits")
    p.add_argument("--sample-size", type=int, default=5000, help="stored vectors to sample")
    p.add_argument("--probes", type=int, default=300, help="hubness probe queries")
    p.add_argument("--probe-k", type=int, default=10, help="neighbours counted per probe")
    p.add_argument("--probe-fetch", type=int, default=60,
                   help="candidates fetched per probe before same-document filtering")
    p.add_argument("--probe-words", default=None,
                   help="text file, one short query per line, used as probes instead of "
                        "stored passages (needs the model)")
    p.add_argument("--top-hubs", type=int, default=15)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--skip-queries", action="store_true", help="skip experiments 1-2 (no model)")
    p.add_argument("--skip-hubness", action="store_true", help="skip experiment 3")
    p.add_argument("--with-text", action="store_true", help="fetch hub text/titles from Postgres")
    p.add_argument("--exact", action="store_true",
                   help="bypass the approximate vector index for query hits and hubness probes")
    p.add_argument("--json-out", default=OUT_DIR / "query_space.json")
    return p.parse_args()


def main():
    args = parse_args()
    import lancedb
    rng = np.random.default_rng(args.seed)
    db = lancedb.connect(str(args.lance_dir))

    print(f"Representation {args.representation}, scale {args.scale}, "
          f"years {args.start_year}-{args.end_year}, seed {args.seed}")
    print(f"Retrieval mode: {'EXACT (vector index bypassed)' if args.exact else 'production (approximate index)'}")
    V_raw, meta, total = sample_stored(db, args, rng)
    V = unit_rows(V_raw)

    report = {"settings": {k: v for k, v in vars(args).items() if k != "json_out"},
              "index_rows_in_range": total}

    # ---- Experiment 2 geometry (needed by experiment 1) ----------------------
    geom, centroid, to_centroid = corpus_geometry(V)
    report["corpus_geometry"] = geom
    print("\n" + "=" * 100 + "\nEXPERIMENT 2: corpus geometry (sample)\n" + "=" * 100)
    print(f"  mean resultant length   : {geom['mean_resultant_length']:.4f}")
    print(f"  mean pairwise cosine    : {geom['mean_pairwise_cosine']:.4f}")
    c = geom["cosine_to_centroid"]
    print(f"  cosine to centroid      : mean {c['mean']:.4f}  std {c['std']:.4f}  "
          f"p01 {c['p01']:.4f}  p99 {c['p99']:.4f}")
    print("  (a high mean pairwise cosine means vectors share a large common direction;\n"
          "   raw cosine then mostly measures closeness to that direction)")

    # ---- Experiment 1 --------------------------------------------------------
    query_hits = {}
    if not args.skip_queries:
        queries = args.queries if args.queries else DEFAULT_QUERIES
        print("\n" + "=" * 100 + "\nEXPERIMENT 1: per-query baselines and z-scored hits\n" + "=" * 100)
        enc = encode_queries(queries, args)
        report["queries"] = []
        header = (f"  {'query':<16}{'enc':<12}{'base mean':>10}{'base std':>9}{'p99':>8}"
                  f"{'top1 sim':>10}{'top1 z':>8}{'top-k z':>9}{'cos→ctr':>9}{'ctr pct':>8}")
        print(header)
        for (q, which), vec in enc.items():
            r = query_baseline(unit(vec), V, centroid, to_centroid, db, args)
            r.update({"query": q, "encoder": which})
            report["queries"].append(r)
            query_hits[(q, which)] = r["hits"]
            b = r["baseline_similarity"]
            print(f"  {q:<16}{which:<12}{b['mean']:>10.4f}{b['std']:>9.4f}{b['p99']:>8.4f}"
                  f"{r['top1_similarity']:>10.4f}{r['top1_z']:>8.2f}{r['topk_mean_z']:>9.2f}"
                  f"{r['query_cosine_to_centroid']:>9.4f}{r['centroid_cosine_percentile_in_sample']:>8.1f}")
        print("\n  base mean/std/p99: cosine between the query and the sampled stored vectors.\n"
              "  top1 z: how many baseline SDs the best hit lies above that query's own mean.\n"
              "  cos→ctr / ctr pct: query cosine to the sample centroid, and its percentile\n"
              "  among the sample's own cosines to the centroid.")

    # ---- Experiment 3 --------------------------------------------------------
    if not args.skip_hubness:
        print("\n" + "=" * 100 + "\nEXPERIMENT 3: hubness\n" + "=" * 100)
        probes, mode = build_probes(args, rng, V, meta)
        print(f"  probing with {len(probes)} {mode}; counting top-{args.probe_k}")
        p_hits, d_hits, row_by_pid, short = run_probes(db, args, rng, V, meta, probes)
        summary = hub_report(p_hits, d_hits, len(probes), args.probe_k, short)
        report["hubness"] = {"mode": mode, "summary": summary}
        print(f"  distinct passages retrieved : {summary['distinct_passages_retrieved']:,} "
              f"of {summary['result_slots']:,} result slots")
        print(f"  Gini of passage counts      : {summary['gini_of_passage_counts']:.3f}")
        print(f"  top-10 passages' slot share : {summary['share_of_slots_top10_passages']:.1%}")
        print(f"  top-10 documents' slot share: {summary['share_of_slots_top10_documents']:.1%}")
        if short:
            print(f"  probes with < k usable hits : {short}")

        hubs = [{"passage_id": pid, "probe_rate": n / len(probes), "count": n,
                 "doc_id": row_by_pid[pid]["doc_id"], "corpus": row_by_pid[pid]["corpus"],
                 "pub_year": row_by_pid[pid]["pub_year"]}
                for pid, n in p_hits.most_common(args.top_hubs)]
        if args.with_text:
            attach_text(hubs, row_by_pid)
        report["hubness"]["top_passages"] = hubs
        report["hubness"]["top_documents"] = [
            {"corpus": c_, "doc_id": d_, "count": n, "probe_rate": n / len(probes)}
            for (c_, d_), n in d_hits.most_common(args.top_hubs)]

        print(f"\n  Top {len(hubs)} hub passages (probe_rate = share of probes that returned it):")
        for h in hubs:
            line = (f"   {h['probe_rate']:6.1%}  n={h['count']:<4} {h['corpus']}/{h['doc_id']} "
                    f"({h['pub_year']})  {h['passage_id'][:12]}…")
            if h.get("title"):
                line += f"  {h['title'][:50]}"
            print(line)
        print(f"\n  Top documents by hub share:")
        for d in report["hubness"]["top_documents"]:
            print(f"   {d['probe_rate']:6.1%}  n={d['count']:<4} {d['corpus']}/{d['doc_id']}")

        if query_hits:
            print("\n  Cross-reference: probe_rate of each query's top hits "
                  "(passage rate / document rate)")
            doc_rate = {did: n / len(probes) for (_, did), n in d_hits.items()}
            cross = []
            for (q, which), hits in query_hits.items():
                rates = [(p_hits.get(h["passage_id"], 0) / len(probes),
                          doc_rate.get(h["doc_id"], 0.0)) for h in hits]
                mp = float(np.mean([r[0] for r in rates])) if rates else 0.0
                md = float(np.mean([r[1] for r in rates])) if rates else 0.0
                cross.append({"query": q, "encoder": which,
                              "mean_passage_probe_rate": mp, "mean_document_probe_rate": md})
                print(f"   {q:<16}{which:<12} mean passage rate {mp:6.2%}   mean doc rate {md:6.2%}")
            report["hubness"]["query_hit_cross_reference"] = cross
        print("\n  Caveat: stored-passage probes are 512-character texts, whereas the queries are\n"
              "  1-4 words; hubness for short queries may differ. Use --probe-words with a list\n"
              "  of short queries to measure that directly.")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(_jsonable(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()