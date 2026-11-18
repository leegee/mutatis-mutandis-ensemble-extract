#!/usr/bin/env python
"""
43_visualise_clusters.py - interactive dark UMAP plot of a clustering run.

Reads the .npz written by 41_cluster_targets.py and passage text/metadata from
Postgres. Writes a self-contained HTML plot (Plotly JS is embedded) that fills
the browser window and has a live publication-year range filter.

Year filtering, two ways:
  * In the page: "From" / "To" sliders (and number boxes) re-filter the points
    instantly; the legend counts update to show how each cluster's size changes
    across the range.
  * On the command line: --min-year / --max-year drop points before the passage
    text is fetched, which keeps the HTML small for big runs.

Examples:
    python 43_visualise_clusters.py --run-id l8-target-form-20261118-101500
    python 43_visualise_clusters.py --run-id YOUR_RUN --words 20
    python 43_visualise_clusters.py --run-id YOUR_RUN --min-year 1500 --max-year 1800
    python 43_visualise_clusters.py --run-id YOUR_RUN --out out/target_runs/clusters.html

Install:
    pip install plotly
"""

from __future__ import annotations

import argparse
import html
import textwrap
from pathlib import Path

import numpy as np

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection

PLOT_DIV_ID = "cluster-plot"

PAGE_CSS = """
html, body { height: 100%; margin: 0; background: #111318; color: #e2e5eb;
             font-family: "Segoe UI", Arial, sans-serif; }
body { display: flex; flex-direction: column; overflow: hidden; }
#bar { flex: 0 0 auto; display: flex; flex-wrap: wrap; align-items: center;
       gap: 6px 22px; padding: 8px 14px; background: #171a21;
       border-bottom: 1px solid #2a2f3a; font-size: 13px; }
#bar .title { font-weight: 600; font-size: 14px; }
#bar .stat { color: #9aa3b2; }
#bar .years { display: flex; align-items: center; gap: 10px; }
#bar label { display: flex; align-items: center; gap: 8px; }
#bar input[type=range] { width: 220px; accent-color: #7aa2ff; }
#bar input[type=number] { width: 66px; background: #252a34; color: #e2e5eb;
       border: 1px solid #3a4150; border-radius: 4px; padding: 3px 5px; }
#bar button { background: #252a34; color: #e2e5eb; border: 1px solid #3a4150;
       border-radius: 4px; padding: 3px 10px; cursor: pointer; }
#bar button:hover { background: #2f3542; }
#plotwrap { flex: 1 1 auto; min-height: 0; }
#plotwrap > div { height: 100%; width: 100%; }
.plotly-graph-div { height: 100% !important; width: 100% !important; }
"""

# Live year filter. Original arrays are kept by reference (the figure is built with
# plain lists, not typed arrays, so gd.data holds them as given) and each change
# re-sends only the points inside the range. Year is customdata[6].
YEAR_FILTER_JS = """
(function () {
  var gd = document.getElementById('__DIV__');
  var lo = document.getElementById('yr-lo'), hi = document.getElementById('yr-hi');
  if (!gd || !lo || !hi) { return; }
  var loN = document.getElementById('yr-lo-num'), hiN = document.getElementById('yr-hi-num');
  var count = document.getElementById('yr-count'), reset = document.getElementById('yr-reset');
  var MIN = +lo.min, MAX = +lo.max;

  var orig = gd.data.map(function (t) {
    return { x: t.x, y: t.y, cd: t.customdata,
             label: (t.meta && t.meta.label) || t.name };
  });
  var total = orig.reduce(function (s, o) { return s + o.x.length; }, 0);
  var pending = false;

  function apply() {
    pending = false;
    var a = +lo.value, b = +hi.value, full = (a <= MIN && b >= MAX);
    var xs = [], ys = [], cds = [], names = [], shown = 0;
    for (var t = 0; t < orig.length; t++) {
      var o = orig[t], X = [], Y = [], C = [];
      for (var i = 0; i < o.x.length; i++) {
        var yr = o.cd[i][6];
        var ok = (yr === null || yr === undefined) ? full : (yr >= a && yr <= b);
        if (ok) { X.push(o.x[i]); Y.push(o.y[i]); C.push(o.cd[i]); }
      }
      xs.push(X); ys.push(Y); cds.push(C);
      names.push(o.label + ' (n=' + X.length.toLocaleString() +
                 (X.length !== o.x.length ? ' of ' + o.x.length.toLocaleString() : '') + ')');
      shown += X.length;
    }
    Plotly.restyle(gd, { x: xs, y: ys, customdata: cds, name: names });
    count.textContent = shown.toLocaleString() + ' of ' + total.toLocaleString() + ' points shown';
  }
  function schedule() { if (!pending) { pending = true; requestAnimationFrame(apply); } }

  function clamp(v) { v = Math.round(+v); return Math.min(MAX, Math.max(MIN, isNaN(v) ? MIN : v)); }
  function set(a, b) {
    a = clamp(a); b = clamp(b);
    if (a > b) { var tmp = a; a = b; b = tmp; }
    lo.value = loN.value = a; hi.value = hiN.value = b;
    schedule();
  }
  lo.addEventListener('input', function () { set(Math.min(+lo.value, +hi.value), hi.value); });
  hi.addEventListener('input', function () { set(lo.value, Math.max(+hi.value, +lo.value)); });
  loN.addEventListener('change', function () { set(loN.value, hi.value); });
  hiN.addEventListener('change', function () { set(lo.value, hiN.value); });
  reset.addEventListener('click', function () { set(MIN, MAX); });

  count.textContent = total.toLocaleString() + ' of ' + total.toLocaleString() + ' points shown';
})();
"""


def wrap_html(value: object, width: int = 40) -> str:
    """Wrap text for Plotly hover labels, escaping corpus text as HTML."""
    value = " ".join(str(value or "").split())
    escaped = html.escape(value)
    return "<br>".join(
        textwrap.wrap(escaped, width=width, break_long_words=True,
                      break_on_hyphens=False)
    )


def fetch_occurrences(conn, occurrence_ids: list[str], words: int,
                      min_year: int | None = None,
                      max_year: int | None = None) -> dict:
    """
    Fetch metadata and a token-window passage for each occurrence.

    The lateral subquery uses the occurrence's own hit_idx, rather than searching
    the passage for the surface form (which may occur more than once).
    With min_year / max_year, out-of-range occurrences are not returned (and their
    passage text is never fetched).
    """
    sql = """
        SELECT
            o.occurrence_id, o.corpus, o.doc_id, o.pub_year, o.hit_idx,
            o.matched_token, d.author, d.title,
            COALESCE(passage.text, '') AS passage
        FROM target_occurrence o
        LEFT JOIN documents d
          ON d.corpus = o.corpus AND d.doc_id = o.doc_id
        LEFT JOIN LATERAL (
            SELECT string_agg(
                CASE WHEN t.token_idx = o.hit_idx
                     THEN '«' || t.token || '»'
                     ELSE t.token
                END,
                ' ' ORDER BY t.token_idx
            ) AS text
            FROM tokens t
            WHERE t.corpus = o.corpus
              AND t.doc_id = o.doc_id
              AND t.token_idx BETWEEN o.hit_idx - %s AND o.hit_idx + %s
        ) passage ON TRUE
        WHERE o.occurrence_id = ANY(%s)
          AND (%s::int IS NULL OR o.pub_year >= %s::int)
          AND (%s::int IS NULL OR o.pub_year <= %s::int)
    """
    result = {}
    # Keep parameter batches moderate for large runs.
    batch_size = 10_000
    with conn.cursor() as cur:
        for start in range(0, len(occurrence_ids), batch_size):
            batch = occurrence_ids[start:start + batch_size]
            cur.execute(sql, (words, words, batch,
                              min_year, min_year, max_year, max_year))
            for row in cur.fetchall():
                (oid, corpus, doc_id, year, hit_idx, token,
                 author, title, passage) = row
                result[oid] = {
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "year": year,
                    "token": token or "",
                    "author": author or "Unknown author",
                    "title": title or doc_id,
                    "passage": passage or "",
                }
    return result


def build_page(fig, run_id: str, n_points: int, n_clusters: int,
               year_bounds: tuple[int, int] | None, use_cdn: bool) -> str:
    """Wrap the figure in a full-viewport page with the year-range controls."""
    controls = ""
    post_script = None
    if year_bounds is not None:
        lo, hi = year_bounds
        controls = f"""
  <div class="years">
    <label>From
      <input id="yr-lo" type="range" min="{lo}" max="{hi}" step="1" value="{lo}">
      <input id="yr-lo-num" type="number" min="{lo}" max="{hi}" step="1" value="{lo}">
    </label>
    <label>To
      <input id="yr-hi" type="range" min="{lo}" max="{hi}" step="1" value="{hi}">
      <input id="yr-hi-num" type="number" min="{lo}" max="{hi}" step="1" value="{hi}">
    </label>
    <button id="yr-reset" type="button">Reset</button>
  </div>
  <span class="stat" id="yr-count"></span>"""
        post_script = YEAR_FILTER_JS.replace("__DIV__", PLOT_DIV_ID)

    fragment = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if use_cdn else True,
        default_width="100%",
        default_height="100%",
        div_id=PLOT_DIV_ID,
        post_script=post_script,
        config={
            "responsive": True,
            "scrollZoom": True,
            "displaylogo": False,
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )

    title = f"Target occurrence clusters · {run_id}"
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{PAGE_CSS}</style>\n</head>\n<body>\n"
        f'<div id="bar">\n  <span class="title">{html.escape(title)}</span>\n'
        f'  <span class="stat">{n_points:,} points · {n_clusters:,} clusters</span>'
        f"{controls}\n</div>\n"
        f'<div id="plotwrap">{fragment}</div>\n</body>\n</html>\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--words", type=int, default=20,
                        help="tokens of context on either side of the hit")
    parser.add_argument("--wrap", type=int, default=40,
                        help="hover-passage wrap width in characters")
    parser.add_argument("--out", default=None, help="output HTML path")
    parser.add_argument("--point-size", type=float, default=5.0)
    parser.add_argument("--min-year", type=int, default=None,
                        help="drop occurrences published before this year")
    parser.add_argument("--max-year", type=int, default=None,
                        help="drop occurrences published after this year")
    parser.add_argument("--noise", action="store_true",
                        help="include HDBSCAN noise (shown in grey)")
    parser.add_argument("--cdn", action="store_true",
                        help="load Plotly from CDN instead of embedding it")
    args = parser.parse_args()

    npz_path = Path(OUT_DIR) / "target_runs" / f"{args.run_id}.npz"
    if not npz_path.exists():
        raise SystemExit(f"Cannot find clustering output: {npz_path}")

    data = np.load(npz_path, allow_pickle=False)
    ids = data["occurrence_id"].astype(str)
    xy = data["e2"]
    labels = data["labels"].astype(int)
    probs = data["probs"]

    if not (len(ids) == len(xy) == len(labels) == len(probs)):
        raise SystemExit("The .npz arrays have inconsistent lengths")

    print(f"Loading metadata and passages for {len(ids):,} occurrences...")
    conn = get_connection(application_name="visualise-target-clusters")
    try:
        metadata = fetch_occurrences(conn, ids.tolist(), args.words,
                                     args.min_year, args.max_year)
    finally:
        conn.close()

    if args.min_year is not None or args.max_year is not None:
        keep = np.fromiter((oid in metadata for oid in ids), dtype=bool, count=len(ids))
        print(f"Year filter kept {int(keep.sum()):,} of {len(keep):,} occurrences")
        if not keep.any():
            raise SystemExit("No occurrences fall inside that year range")
        ids, xy, labels, probs = ids[keep], xy[keep], labels[keep], probs[keep]
    else:
        missing = len(ids) - len(metadata)
        if missing:
            print(f"Warning: {missing:,} occurrences had no matching metadata row")

    years = [m["year"] for m in metadata.values() if m["year"] is not None]
    year_bounds = (int(min(years)), int(max(years))) if years else None

    import plotly.graph_objects as go
    from plotly.colors import qualitative

    fig = go.Figure()
    palette = qualitative.Dark24
    cluster_ids = sorted(c for c in set(labels.tolist()) if c >= 0)
    if args.noise and np.any(labels == -1):
        cluster_ids = [-1] + cluster_ids

    for cluster in cluster_ids:
        idx = np.flatnonzero(labels == cluster)
        if not len(idx):
            continue

        # customdata columns: 0 year text, 1 heading, 2 corpus/doc, 3 passage,
        # 4 occurrence id, 5 membership, 6 numeric year (used by the page's filter)
        custom = []
        for i in idx:
            m = metadata.get(ids[i])
            if m is None:
                custom.append(["?", "Unknown", "No metadata", "", ids[i], 0.0, None])
                continue

            heading = f"{m['author']}, {m['title']}"
            passage = wrap_html(m["passage"], args.wrap)
            custom.append([
                str(m["year"]),
                wrap_html(heading, args.wrap),
                wrap_html(f"{m['corpus']} / {m['doc_id']}", args.wrap),
                passage,
                ids[i],
                float(probs[i]),
                int(m["year"]) if m["year"] is not None else None,
            ])

        is_noise = cluster == -1
        label = "Noise" if is_noise else f"Cluster {cluster}"
        colour = "#777777" if is_noise else palette[(cluster if cluster >= 0 else 0) % len(palette)]

        fig.add_trace(go.Scattergl(
            # Plain lists (not numpy) so the page's filter can read them back as given.
            x=np.round(xy[idx, 0], 4).tolist(),
            y=np.round(xy[idx, 1], 4).tolist(),
            mode="markers",
            name=f"{label} (n={len(idx):,})",
            meta=dict(label=label),
            marker=dict(
                size=3 if is_noise else args.point_size,
                color=colour,
                opacity=0.25 if is_noise else 0.78,
            ),
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "%{customdata[0]}<br>"
                "<span style='color:#aaaaaa'>%{customdata[2]}</span><br><br>"
                "%{customdata[3]}<br><br>"
                "<span style='color:#aaaaaa'>"
                "Membership: %{customdata[5]:.2f}<br>"
                "Occurrence: %{customdata[4]}"
                "</span><extra></extra>"
            ),
        ))

    fig.update_layout(
        template="plotly_dark",
        autosize=True,                      # fill the container; no fixed height
        paper_bgcolor="#111318",
        plot_bgcolor="#171a21",
        font=dict(family="Segoe UI, Arial, sans-serif", color="#e2e5eb", size=12),
        hoverlabel=dict(
            bgcolor="#252a34",
            bordercolor="#596273",
            font=dict(family="Segoe UI, Arial, sans-serif", size=16,
                      color="#f2f3f5"),
            align="left",
        ),
        xaxis=dict(title="UMAP 1", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        yaxis=dict(title="UMAP 2", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        legend=dict(
            title="Clusters · click to hide/show",
            bgcolor="rgba(20,23,30,0.85)",
            bordercolor="#343b48",
            borderwidth=1,
            itemsizing="constant",
            y=1,
            yanchor="top",
            x=1.01,
        ),
        margin=dict(l=55, r=230, t=20, b=50),
        hovermode="closest",
    )

    out_path = Path(args.out) if args.out else (
        Path(OUT_DIR) / "target_runs" / f"{args.run_id}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        build_page(fig, args.run_id, len(ids), len(set(labels[labels >= 0].tolist())),
                   year_bounds, args.cdn),
        encoding="utf-8",
    )

    print(f"Saved: {out_path}")
    print(f"Points: {len(ids):,} | clusters: {len(set(labels[labels >= 0])):,} "
          f"| noise: {(labels == -1).sum():,}")
    print(f"Open the HTML file in your browser. {out_path}")


if __name__ == "__main__":
    main()