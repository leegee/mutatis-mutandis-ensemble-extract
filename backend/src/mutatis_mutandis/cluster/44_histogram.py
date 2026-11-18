#!/usr/bin/env python3
"""Plot the number of dated texts per 50-year period.

Reads publication years from the PostgreSQL `documents` table and writes
an interactive, dark-themed Plotly histogram.

Required environment:
    DATABASE_URL=postgresql://user:password@host:5432/database

Or use the standard PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD variables.
"""

from __future__ import annotations

import os
from collections import Counter

import plotly.graph_objects as go

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_config import OUT_DIR


START_YEAR = -600
END_YEAR = 1625
PERIOD_YEARS = 25
OUTPUT_FILE = OUT_DIR / "texts_by_period.html"


def load_years() -> list[int]:
    """Return the publication year of each dated document."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pub_year
                FROM documents
                WHERE pub_year IS NOT NULL
                  AND pub_year BETWEEN %s AND %s
                """,
                (START_YEAR, END_YEAR),
            )
            return [int(row[0]) for row in cur.fetchall()]


def period_start(year: int) -> int:
    """Map a year to a 50-year period anchored at START_YEAR."""
    return START_YEAR + ((year - START_YEAR) // PERIOD_YEARS) * PERIOD_YEARS


def format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    if year == 0:
        return "AD 1"
    return f"AD {year}"


def main() -> None:
    years = load_years()
    if not years:
        raise SystemExit(
            f"No dated documents found between {format_year(START_YEAR)} "
            f"and {format_year(END_YEAR)}."
        )

    counts = Counter(period_start(year) for year in years)

    # Include only populated periods. The final period is clipped at END_YEAR.
    periods = sorted(start for start, count in counts.items() if count > 0)

    labels = [
        f"{format_year(start)}–{format_year(min(start + PERIOD_YEARS - 1, END_YEAR))}"
        for start in periods
    ]

    values = [counts[start] for start in periods]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker=dict(color="#75aadb", line=dict(color="#a8c9e8", width=0.6)),
            hovertemplate="%{x}<br>%{y:,} texts<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(
            text="Texts by 50-year period",
            x=0.02,
            xanchor="left",
            font=dict(size=20, color="#eeeeee"),
        ),
        template="plotly_dark",
        paper_bgcolor="#17191f",
        plot_bgcolor="#20232b",
        font=dict(color="#d8dbe2"),
        xaxis=dict(
            title="Publication period",
            tickangle=-90,  # vertical labels, read bottom-to-top
            tickfont=dict(size=10),
            automargin=True,
            showgrid=False,
            type="category",
        ),
        yaxis=dict(
            title="Number of texts",
            rangemode="tozero",
            gridcolor="#3a3e48",
            zerolinecolor="#555b68",
        ),
        margin=dict(l=75, r=30, t=75, b=180),
        bargap=0.16,
        hoverlabel=dict(
            bgcolor="#292e38",
            bordercolor="#697386",
            font=dict(color="#ffffff"),
        ),
    )

    fig.write_html(OUTPUT_FILE, include_plotlyjs=True, full_html=True)
    print(f"Found {len(years):,} dated texts across {len(periods)} populated periods.")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
