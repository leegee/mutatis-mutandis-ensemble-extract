#!/usr/bin/env python3

from pathlib import Path

import matplotlib.pyplot as plt

from lib.corpus_db import get_connection


OUTPUT_PATH = Path("document_size_by_year.png")


def main() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pub_year,
                    MIN(token_count) AS min_tokens,
                    SUM(token_count) AS total_tokens,
                    COUNT(*) AS document_count,
                    MAX(token_count) AS max_tokens
                FROM documents
                WHERE pub_year IS NOT NULL
                  AND token_count > 0
                GROUP BY pub_year
                ORDER BY pub_year
                """
            )
            rows = cur.fetchall()

    if not rows:
        raise RuntimeError("No document size data found")

    years = [row[0] for row in rows]
    minimums = [row[1] for row in rows]
    totals = [row[2] for row in rows]
    counts = [row[3] for row in rows]
    maximums = [row[4] for row in rows]

    cumulative_total = 0
    cumulative_count = 0
    cumulative_averages = []

    for total, count in zip(totals, counts):
        cumulative_total += total
        cumulative_count += count
        cumulative_averages.append(
            cumulative_total / cumulative_count
        )

    fig, ax = plt.subplots(figsize=(14, 7))

    ax.vlines(
        years,
        minimums,
        maximums,
        linewidth=2,
        label="Min–max",
    )

    ax.plot(
        years,
        cumulative_averages,
        marker="o",
        color="orange",
        linewidth=2,
        label="Cumulative average",
    )

    ax.set_title("Document size by publication year")
    ax.set_xlabel("Publication year")
    ax.set_ylabel("Tokens")

    ax.set_yscale("log")

    ax.tick_params(axis="x", rotation=90)
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)
    plt.show()


if __name__ == "__main__":
    main()
