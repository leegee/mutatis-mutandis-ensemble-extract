#!/usr/bin/env python3
"""
scripts/diagnose_retrieval_exactness.py

Read-only check of whether LanceDB search (via the project's search_passages())
returns the TRUE nearest neighbours.

Background: in the query-space diagnostic, the best stored vector in the random
sample was more similar to the query than the retrieved top-1 for four of the
five test queries. Since the sample is a subset of the index, that means the
search missed closer passages. This script establishes whether, how much, and
why.

Method
------
* Load every vector that matches the filters (year range + scale) from all
  candidate tables and compute the exact top-k by brute force in numpy.
* Compare with search_passages() (the production path) and with variants built
  directly on LanceDB, each changing one thing:
    replica            same call as search_passages (harness sanity check)
    prefilter=False    filter applied after the ANN step
    bypass_vector_index exact scan inside Lance, filter applied first
    nprobes+refine     more thorough ANN search
* Report recall@k (by passage_id, and tie-tolerant, since duplicate passages
  have identical vectors), the top-1 similarity gap against the exact answer,
  and the error between the distances Lance reports and the exact ones.
* Also print the LanceDB version, the prefilter default, and each table's
  indices, and repeat the comparison with random stored vectors as queries to
  see whether the problem is general or specific to outlying (short) queries.

Run from the backend directory:

    python scripts/diagnose_retrieval_exactness.py
    python scripts/diagnose_retrieval_exactness.py --encoder both --probe-stored 50
    python scripts/diagnose_retrieval_exactness.py --skip-queries     # no model needed

Only LanceDB is used (no Postgres). Nothing is modified except the JSON report.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

# --- make `mutatis_mutandis` (and sibling scripts) importable ----------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import numpy as np  # noqa: E402

from mutatis_mutandis.lib.corpus_config import LANCE_INDEXES_DIR, OUT_DIR  # noqa: E402

DEFAULT_QUERIES = ["noah", "asdfasdfasdf", "white hair", "white-haired", "albino"]
REPRESENTATIONS = ("l8", "last", "mean4")
TIE_TOL = 1e-6          # similarity tolerance when deciding two hits are tied
VARIANTS = ("production", "replica", "prefilter=False", "bypass_vector_index", "nprobes+refine")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unit(v):
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    return v / np.linalg.norm(v)


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
# Environment and index information
# ---------------------------------------------------------------------------

def describe_environment(db, tables):
    import lancedb
    from lancedb.query import LanceQueryBuilder

    info = {"lancedb_version": lancedb.__version__, "tables": {}}
    try:
        sig = inspect.signature(LanceQueryBuilder.where)
        default = sig.parameters["prefilter"].default
        info["where_prefilter_default"] = default
    except Exception as exc:  # noqa: BLE001
        info["where_prefilter_default"] = f"unknown ({exc})"

    print(f"LanceDB version: {info['lancedb_version']}")
    print(f"where(prefilter=...) default in this version: {info['where_prefilter_default']}")

    any_index = False
    for name in tables:
        tbl = db.open_table(name)
        entry = {"rows": tbl.count_rows()}
        try:
            entry["vector_type"] = str(tbl.schema.field("vector").type)
        except Exception:  # noqa: BLE001
            entry["vector_type"] = "unknown"
        try:
            idx = tbl.list_indices()
            entry["indices"] = [
                {"name": getattr(i, "name", None),
                 "type": str(getattr(i, "index_type", None)),
                 "columns": list(getattr(i, "columns", []) or [])}
                for i in idx
            ]
        except Exception as exc:  # noqa: BLE001
            entry["indices"] = f"list_indices failed: {exc}"
        any_index = any_index or bool(entry["indices"]) and isinstance(entry["indices"], list)
        info["tables"][name] = entry

    print(f"\nTables ({len(tables)}):")
    for name, e in info["tables"].items():
        print(f"  {name}: {e['rows']:,} rows, vector {e['vector_type']}, indices: {e['indices']}")
    info["any_vector_index"] = any_index
    if not any_index:
        print("\n  No indices reported: Lance does an exact flat scan, so recall should be 1.0.\n"
              "  Any shortfall would then point at filtering, not at an ANN index.")
    return info


# ---------------------------------------------------------------------------
# Exact (brute-force) neighbours
# ---------------------------------------------------------------------------

def load_all_vectors(db, tables, where, max_rows):
    cols = ["passage_id", "doc_id", "vector"]
    counts = {n: db.open_table(n).count_rows(where) for n in tables}
    total = sum(counts.values())
    if total == 0:
        raise SystemExit(f"No rows match: {where}")
    if total > max_rows:
        raise SystemExit(f"{total:,} matching rows exceeds --max-rows {max_rows:,}; "
                         "raise it if you have the memory (rows x dim x 4 bytes).")
    ids, docs, vecs = [], [], []
    for name in tables:
        if counts[name] == 0:
            continue
        arrow = (db.open_table(name).search().where(where).select(cols)
                 .limit(counts[name]).to_arrow())
        col = arrow.column("vector").combine_chunks()
        vecs.append(col.values.to_numpy(zero_copy_only=False)
                    .reshape(-1, col.type.list_size).astype(np.float32))
        ids += arrow.column("passage_id").to_pylist()
        docs += arrow.column("doc_id").to_pylist()
    M = np.concatenate(vecs, axis=0)
    M /= np.linalg.norm(M, axis=1, keepdims=True)
    pid_index = {}
    for i, p in enumerate(ids):
        pid_index.setdefault(p, i)
    return M, ids, docs, pid_index


def exact_topk(M, q, k):
    sims = M @ q
    k = min(k, sims.size)
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return idx, sims


# ---------------------------------------------------------------------------
# Search variants
# ---------------------------------------------------------------------------

def lance_search(handles, q, where, limit, *, prefilter=True, bypass=False,
                 nprobes=None, refine=None):
    """Per-table search merged by distance; mirrors core.search_passages."""
    rows = []
    for name, tbl in handles.items():
        qb = tbl.search(q, vector_column_name="vector").metric("cosine")
        if nprobes:
            qb = qb.nprobes(nprobes)
        if refine:
            qb = qb.refine_factor(refine)
        if bypass:
            qb = qb.bypass_vector_index()
        arrow = (qb.where(where, prefilter=prefilter)
                 .select(["passage_id", "doc_id", "_distance"])
                 .limit(limit).to_arrow())
        rows += arrow.to_pylist()
    rows.sort(key=lambda r: r["_distance"])
    return [{"passage_id": r["passage_id"], "doc_id": r["doc_id"],
             "distance": float(r["_distance"])} for r in rows[:limit]]


def run_variant(name, db, handles, q, args, where):
    from mutatis_mutandis.core import search_passages
    if name == "production":
        rows = search_passages(
            db=db, query_vector=q, representation=args.representation,
            start_year=args.start_year, end_year=args.end_year, limit=args.limit,
            include_vectors=False, negative_vectors=None, scale=args.scale)
        return [{"passage_id": r["passage_id"], "doc_id": r["doc_id"],
                 "distance": float(r["distance"])} for r in rows]
    if name == "replica":
        return lance_search(handles, q, where, args.limit)
    if name == "prefilter=False":
        return lance_search(handles, q, where, args.limit, prefilter=False)
    if name == "bypass_vector_index":
        return lance_search(handles, q, where, args.limit, bypass=True)
    if name == "nprobes+refine":
        return lance_search(handles, q, where, args.limit,
                            nprobes=args.nprobes, refine=args.refine_factor)
    raise ValueError(name)


def score_variant(hits, exact_idx, sims, ids, pid_index, k):
    kth = sims[exact_idx[-1]]
    exact_ids = {ids[i] for i in exact_idx}
    got = [h["passage_id"] for h in hits]
    in_universe = [p for p in got if p in pid_index]
    id_recall = len(set(got) & exact_ids) / k
    tol_recall = sum(1 for p in in_universe if sims[pid_index[p]] >= kth - TIE_TOL) / k
    errs = [abs(h["distance"] - (1.0 - float(sims[pid_index[h["passage_id"]]])))
            for h in hits if h["passage_id"] in pid_index]
    top1 = 1.0 - hits[0]["distance"] if hits else None
    return {
        "returned": len(hits),
        "recall_ids": id_recall,
        "recall_tie_tolerant": tol_recall,
        "top1_similarity": top1,
        "top1_gap_vs_exact": (float(sims[exact_idx[0]]) - top1) if top1 is not None else None,
        "dist_abs_err_max": float(max(errs)) if errs else None,
        "dist_abs_err_mean": float(np.mean(errs)) if errs else None,
        "outside_exact_universe": len(got) - len(in_universe),
    }


def evaluate(q, db, handles, M, ids, pid_index, args, where, variants):
    q = unit(q)
    exact_idx, sims = exact_topk(M, q, args.limit)
    out = {"exact_top1_similarity": float(sims[exact_idx[0]]),
           "exact_topk_similarity": [float(sims[i]) for i in exact_idx],
           "variants": {}, "_hits": {}}
    for v in variants:
        try:
            hits = run_variant(v, db, handles, q, args, where)
            out["variants"][v] = score_variant(hits, exact_idx, sims, ids, pid_index, args.limit)
            out["_hits"][v] = [h["passage_id"] for h in hits]
        except Exception as exc:  # noqa: BLE001
            out["variants"][v] = {"error": f"{type(exc).__name__}: {exc}"}
    if "production" in out["_hits"] and "replica" in out["_hits"]:
        out["replica_matches_production"] = out["_hits"]["production"] == out["_hits"]["replica"]
    return out


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_eval(label, ev, k):
    print(f"\n  {label}   (exact top-1 similarity {ev['exact_top1_similarity']:.4f})")
    print(f"    {'variant':<22}{'returned':>9}{'recall@'+str(k):>10}{'tie-tol':>9}"
          f"{'top1 sim':>10}{'top1 gap':>10}{'max |Δdist|':>13}{'outside':>9}")
    for v, s in ev["variants"].items():
        if "error" in s:
            print(f"    {v:<22}  ERROR {s['error'][:90]}")
            continue
        def f(x, spec):
            return format(x, spec) if x is not None else "-"
        print(f"    {v:<22}{s['returned']:>9}{s['recall_ids']:>10.2f}{s['recall_tie_tolerant']:>9.2f}"
              f"{f(s['top1_similarity'], '.4f'):>10}{f(s['top1_gap_vs_exact'], '.4f'):>10}"
              f"{f(s['dist_abs_err_max'], '.5f'):>13}{s['outside_exact_universe']:>9}")
    if "replica_matches_production" in ev:
        print(f"    replica reproduces production result list: {ev['replica_matches_production']}")


def mean_metric(evals, variant, key):
    vals = [e["variants"][variant][key] for e in evals
            if variant in e["variants"] and key in e["variants"][variant]
            and e["variants"][variant][key] is not None]
    return float(np.mean(vals)) if vals else None


def verdict(evals, label, prefilter_default):
    prod = mean_metric(evals, "production", "recall_tie_tolerant")
    byp = mean_metric(evals, "bypass_vector_index", "recall_tie_tolerant")
    nopre = mean_metric(evals, "prefilter=False", "recall_tie_tolerant")
    more = mean_metric(evals, "nprobes+refine", "recall_tie_tolerant")
    derr = mean_metric(evals, "production", "dist_abs_err_max")
    print(f"\n  Reading for {label}:")
    if prod is None:
        print("    production variant failed; see errors above.")
        return
    print(f"    mean tie-tolerant recall@k: production {prod:.2f}"
          + (f", bypass index {byp:.2f}" if byp is not None else "")
          + (f", prefilter=False {nopre:.2f}" if nopre is not None else "")
          + (f", nprobes+refine {more:.2f}" if more is not None else ""))
    if prod >= 0.99:
        print("    Production search is effectively exact for these queries.")
        return
    if byp is not None and byp >= 0.99:
        print("    Exact Lance scan matches brute force but production does not: the shortfall\n"
              "    comes from the approximate vector index (or its settings), not from the data\n"
              "    or the filter. See whether 'nprobes+refine' recovers it.")
    elif byp is not None:
        print("    Even Lance's exact scan disagrees with brute force. Suspect filter semantics,\n"
              "    stored-vs-sampled vector mismatch, or duplicate rows; inspect 'outside' counts.")
    if nopre is not None and nopre < prod - 0.01:
        print("    prefilter=False is worse than production, so production is pre-filtering and\n"
              "    the filter position is not the cause.")
    elif prefilter_default is False:
        print("    This LanceDB version defaults where() to prefilter=False, so production\n"
              "    post-filters: the ANN step takes the nearest rows across ALL scales/years and\n"
              "    the filter then discards non-matching ones, losing true hits. Compare the\n"
              "    'returned' column (fewer than the limit is the signature). The fix would be\n"
              "    where(..., prefilter=True) in core.search_passages (not applied here).")
    if derr is not None and derr > 1e-3:
        print(f"    Reported distances differ from exact ones by up to {derr:.4f}: consistent with\n"
              "    quantised (PQ) distances. Raising refine_factor re-ranks with exact vectors.")


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
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--probe-stored", type=int, default=30,
                   help="also test this many random stored vectors as queries (0 to skip)")
    p.add_argument("--nprobes", type=int, default=64, help="for the nprobes+refine variant")
    p.add_argument("--refine-factor", type=int, default=20, help="for the nprobes+refine variant")
    p.add_argument("--max-rows", type=int, default=500_000,
                   help="refuse to brute-force more matching rows than this")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--skip-queries", action="store_true", help="skip text queries (no model)")
    p.add_argument("--json-out", default=OUT_DIR / "retrieval_exactness.json")
    return p.parse_args()


def main():
    args = parse_args()
    import lancedb
    from mutatis_mutandis.core import candidate_tables

    rng = np.random.default_rng(args.seed)
    db = lancedb.connect(str(args.lance_dir))
    where = where_clause(args)
    tables = candidate_tables(db, args.representation, args.start_year, args.end_year)
    if not tables:
        raise SystemExit("No candidate tables for these settings")
    handles = {n: db.open_table(n) for n in tables}

    print("=" * 100 + "\nENVIRONMENT\n" + "=" * 100)
    report = {"settings": {k: v for k, v in vars(args).items() if k != "json_out"},
              "environment": describe_environment(db, tables)}

    pf_default = report["environment"].get("where_prefilter_default")
    print("\nLoading all matching vectors for brute-force comparison ...")
    M, ids, docs, pid_index = load_all_vectors(db, tables, where, args.max_rows)
    print(f"  {M.shape[0]:,} vectors, dim {M.shape[1]}; filter: {where}")
    report["rows_in_universe"] = int(M.shape[0])

    query_evals, stored_evals = [], []

    if not args.skip_queries:
        from diagnose_query_space import encode_queries  # sibling script
        queries = args.queries if args.queries else DEFAULT_QUERIES
        print("\n" + "=" * 100 + "\nTEXT QUERIES\n" + "=" * 100)
        enc = encode_queries(queries, args)
        report["queries"] = []
        for (q, which), vec in enc.items():
            ev = evaluate(vec, db, handles, M, ids, pid_index, args, where, VARIANTS)
            print_eval(f"{q!r} [{which}]", ev, args.limit)
            query_evals.append(ev)
            report["queries"].append({"query": q, "encoder": which,
                                      **{k: v for k, v in ev.items() if k != "_hits"}})
        verdict(query_evals, "text queries", pf_default)

    if args.probe_stored > 0:
        n = min(args.probe_stored, M.shape[0])
        print("\n" + "=" * 100 + f"\nRANDOM STORED VECTORS AS QUERIES (n={n})\n" + "=" * 100)
        for i in rng.choice(M.shape[0], size=n, replace=False):
            stored_evals.append(evaluate(M[i], db, handles, M, ids, pid_index, args, where, VARIANTS))
        print(f"  {'variant':<22}{'mean recall':>12}{'mean tie-tol':>14}{'mean max|Δdist|':>17}")
        summary = {}
        for v in VARIANTS:
            r = mean_metric(stored_evals, v, "recall_ids")
            t = mean_metric(stored_evals, v, "recall_tie_tolerant")
            d = mean_metric(stored_evals, v, "dist_abs_err_max")
            summary[v] = {"mean_recall_ids": r, "mean_recall_tie_tolerant": t, "mean_max_dist_err": d}
            if t is None:
                print(f"  {v:<22}  (variant failed)")
            else:
                print(f"  {v:<22}{r:>12.3f}{t:>14.3f}{(d if d is not None else float('nan')):>17.5f}")
        report["stored_vector_queries"] = {"n": n, "summary": summary}
        verdict(stored_evals, "stored-vector queries", pf_default)
        print("\n  If stored-vector queries are near-exact but text queries are not, the index\n"
              "  struggles with out-of-distribution (short) query vectors specifically.")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(_jsonable(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()