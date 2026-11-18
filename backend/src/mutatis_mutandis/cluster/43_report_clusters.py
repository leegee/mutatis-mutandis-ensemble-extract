
#!/usr/bin/env python

"""
43_report_clusters.py - automatically produce a readable report of a clustering run.

Uses 42_inspect_clusters.py to collect the overview and passage exemplars,
then assembles them into a Markdown report.

Examples:
    python 43_report_clusters.py
    python 43_report_clusters.py --top 15
    python 43_report_clusters.py --run-id l8-target-form-20261118-101500
    python 43_report_clusters.py --top 20 --n 8 --words 25
    python 43_report_clusters.py --all-clusters

The report includes:
    - Run parameters and confound diagnostics
    - Complete cluster summary table
    - Nearest-to-centre exemplars for selected clusters
    - Random-member exemplars for the same clusters
    - A short checklist for interpreting the results
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import logger


INSPECTOR = Path(__file__).with_name("42_inspect_clusters.py")


def latest_run(cur) -> str:
    cur.execute(
        """
        SELECT run_id
        FROM target_projection_run
        ORDER BY created_at DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit("No clustering runs found.")
    return row[0]


def get_clusters(cur, run_id: str, top: int, all_clusters: bool) -> list[int]:
    """Return cluster IDs ordered by descending size."""
    sql = """
        SELECT cluster
        FROM target_cluster_summary
        WHERE run_id = %s
          AND cluster >= 0
        ORDER BY n DESC
    """
    params = [run_id]

    if not all_clusters:
        sql += " LIMIT %s"
        params.append(top)

    cur.execute(sql, params)
    return [row[0] for row in cur.fetchall()]


def run_inspector(
    run_id: str,
    *,
    clusters: list[int] | None = None,
    n: int = 8,
    words: int = 25,
    table: int = 50,
    sample: bool = False,
) -> str:
    """Run 42_inspect_clusters.py and return its output."""
    cmd = [
        "uv",
        "run",
        "python",
        str(INSPECTOR),
        "--run-id", run_id,
        "--n", str(n),
        "--words", str(words),
        "--table", str(table),
    ]

    if clusters:
        for cluster in clusters:
            cmd.extend(["--cluster", str(cluster)])

    if sample:
        cmd.append("--sample")

    logger.info("Running: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output = result.stdout
    if result.stderr:
        output += "\n" + result.stderr

    if result.returncode:
        raise RuntimeError(
            f"42_inspect_clusters.py failed ({result.returncode}):\n{output}"
        )

    return output.strip()


def build_report(
    run_id: str,
    clusters: list[int],
    *,
    n: int,
    words: int,
    table: int,
) -> str:
    """Collect all sections and assemble the Markdown report."""
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    logger.info("Collecting run overview and cluster table")
    overview = run_inspector(
        run_id,
        n=n,
        words=words,
        table=table,
    )

    sections = [
        "# Clustering inspection report",
        "",
        f"- **Run:** `{run_id}`",
        f"- **Generated:** {generated}",
        f"- **Clusters inspected:** {len(clusters)}",
        f"- **Exemplars per view:** {n}",
        f"- **Context:** {words} words either side of the hit",
        "",
        "---",
        "",
        "## 1. Run overview and cluster summary",
        "",
        "```text",
        overview,
        "```",
        "",
        "---",
        "",
        "## 2. Cluster inspections",
        "",
        "Each selected cluster is shown twice:",
        "",
        "- **Nearest to centre:** the most representative passages.",
        "- **Random members:** a less selective view of cluster composition.",
        "",
        "Compare the two. A coherent centre with a heterogeneous random sample "
        "may indicate a broad or internally mixed cluster.",
        "",
    ]

    for index, cluster in enumerate(clusters, start=1):
        logger.info(
            "Inspecting cluster %s (%s of %s)",
            cluster, index, len(clusters),
        )

        nearest = run_inspector(
            run_id,
            clusters=[cluster],
            n=n,
            words=words,
        )

        random = run_inspector(
            run_id,
            clusters=[cluster],
            n=n,
            words=words,
            sample=True,
        )

        sections.extend([
            f"### Cluster {cluster}",
            "",
            "#### Nearest to centre",
            "",
            nearest,
            "",
            "#### Random members",
            "",
            random,
            "",
            "---",
            "",
        ])

    sections.extend([
        "## 3. Interpretation checklist",
        "",
        "For each cluster, consider:",
        "",
        "- [ ] Do the passages share a recognisable descriptive or semantic pattern?",
        "- [ ] Is the pattern present in both the nearest and random samples?",
        "- [ ] Are multiple documents represented?",
        "- [ ] Is one document disproportionately influential?",
        "- [ ] Does the cluster span a meaningful chronological period?",
        "- [ ] Is the cluster primarily lexical (different forms of the same word)?",
        "- [ ] Could the grouping be explained by corpus or retrieval route?",
        "- [ ] Is there a plausible historical or literary interpretation?",
        "",
        "## 4. Research notes",
        "",
        "### Strong or coherent clusters",
        "",
        "### Interesting but ambiguous clusters",
        "",
        "### Chronological patterns",
        "",
        "### Document-specific clusters",
        "",
        "### Possible confounds",
        "",
        "### Clusters requiring further investigation",
        "",
    ])

    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    parser.add_argument("--run-id", help="Run to inspect; defaults to latest")
    parser.add_argument("--top", type=int, default=12,
                        help="Number of largest clusters to inspect (default: 12)")
    parser.add_argument("--all-clusters", action="store_true",
                        help="Inspect every non-noise cluster")
    parser.add_argument("--n", type=int, default=6,
                        help="Exemplars per cluster per view (default: 6)")
    parser.add_argument("--words", type=int, default=25,
                        help="Context words either side of hit (default: 25)")
    parser.add_argument("--table", type=int, default=50,
                        help="Number of clusters in overview table")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output Markdown file")

    args = parser.parse_args()

    if not INSPECTOR.exists():
        raise SystemExit(f"Inspector not found: {INSPECTOR}")

    conn = get_connection(application_name="cluster-report")

    try:
        with conn.cursor() as cur:
            run_id = args.run_id or latest_run(cur)
            clusters = get_clusters(
                cur,
                run_id,
                args.top,
                args.all_clusters,
            )
    finally:
        conn.close()

    if not clusters:
        raise SystemExit(f"No non-noise clusters found for run {run_id}")

    logger.info(
        "Preparing report for run %s: %s clusters",
        run_id, len(clusters),
    )

    report = build_report(
        run_id,
        clusters,
        n=args.n,
        words=args.words,
        table=args.table,
    )

    if args.output:
        output_path = args.output
    else:
        output_dir = Path(OUT_DIR) / "target_runs" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"cluster-report-{run_id}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    logger.info("Report written to %s", output_path)
    logger.info("Inspected %s clusters", len(clusters))


if __name__ == "__main__":
    main()
