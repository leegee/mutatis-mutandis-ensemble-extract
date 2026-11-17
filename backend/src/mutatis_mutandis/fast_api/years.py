"""
mutatis_mutandis/years.py

The upper bound for publication-year ranges is the current year, evaluated at
call time so a long-running server does not go stale on 1 January.
"""

from __future__ import annotations

from datetime import date


def current_year() -> int:
    return date.today().year
