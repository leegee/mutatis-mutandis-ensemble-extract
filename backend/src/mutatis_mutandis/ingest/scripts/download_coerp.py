#!/usr/bin/env python3
"""Download available COERP TEI records dated through 1650.

COERP's public site has period listings and per-record XML URLs, but no
documented corpus-wide archive. This script collects IDs from the period
pages, downloads each TEI XML once, and writes a CSV manifest.

Usage:
    python download_coerp.py --output G:/corpus/coerp

Requires Python 3.10+ and the standard library only.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import OUT_DIR


BASE = "https://coerp.uni-koeln.de"
PERIOD_PAGES = (
    # The early-period facets are empty in the released corpus; available
    # records begin in 1500. Include 1650-1699 so year 1650 can be filtered
    # from that listing using the TEI header date.
    "1500-1549",
    "1550-1599",
    "1600-1649",
    "1650-1699",  # Filtered to 1650 using the TEI header date.
)
TEI_NS = "{http://www.tei-c.org/ns/1.0}"


class RecordLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        path = urllib.parse.urlparse(href).path.rstrip("/")
        match = re.fullmatch(r"/text/([^/]+)", path)
        if match:
            self.ids.add(urllib.parse.unquote(match.group(1)))


class ServerRejectedRequest(RuntimeError):
    """Raised when COERP rejects automated requests with HTTP 418."""


def fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "COERP-research-downloader/1.0 (polite, sequential requests)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 418:
            raise ServerRejectedRequest(
                f"COERP returned HTTP 418 for {url}; stopping to avoid further rejected requests. "
                "Use the interactive site or request a research download from the project team."
            ) from exc
        raise


def records_from_period(period: str, timeout: int) -> set[str]:
    url = f"{BASE}/periods/{period}/title"
    parser = RecordLinkParser()
    parser.feed(fetch(url, timeout).decode("utf-8", errors="replace"))
    return parser.ids


def header_fields(xml_bytes: bytes) -> tuple[int | None, str, str]:
    root = ET.fromstring(xml_bytes)
    if root.tag != f"{TEI_NS}TEI":
        raise ValueError("Response is XML but not a TEI document")

    title = root.find(f".//{TEI_NS}title[@type='short']")
    if title is None:
        title = root.find(f".//{TEI_NS}title")
    author = root.find(f".//{TEI_NS}author[@role='author']")

    date_values: list[str] = []
    for element in root.findall(f".//{TEI_NS}sourceDesc//{TEI_NS}date"):
        value = element.get("when") or (element.text or "").strip()
        if value:
            date_values.append(value)
    year = None
    for value in date_values:
        match = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", value)
        if match:
            year = int(match.group(1))
            break
    return year, (title.text or "").strip() if title is not None else "", (author.text or "").strip() if author is not None else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT_DIR / 'coerp', help="Directory for TEI files and manifest.csv")
    parser.add_argument("--through", type=int, default=1650, help="Latest publication year to include (default: 1650)")
    parser.add_argument("--delay", type=float, default=0.75, help="Seconds between requests (default: 0.75)")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    all_ids: set[str] = set()
    for period in PERIOD_PAGES:
        try:
            ids = records_from_period(period, args.timeout)
            print(f"{period}: found {len(ids)} record links")
            all_ids.update(ids)
        except ServerRejectedRequest as exc:
            print(f"{period}: listing failed: {exc}")
            print("Stopped. No further requests were sent.")
            return 2
        except Exception as exc:
            print(f"{period}: listing failed: {exc}")
        time.sleep(max(0.0, args.delay))

    rows: list[dict[str, str | int]] = []
    server_blocked = False
    for index, record_id in enumerate(sorted(all_ids), start=1):
        url = f"{BASE}/text/{urllib.parse.quote(record_id, safe='_-.')}/xml"
        path = args.output / f"{record_id}.xml"
        try:
            data = fetch(url, args.timeout)
            year, title, author = header_fields(data)
            if year is not None and year > args.through:
                status = "excluded_after_cutoff"
            else:
                path.write_bytes(data)
                status = "downloaded" if year is not None else "downloaded_date_unresolved"
            rows.append({
                "record_id": record_id,
                "year": year if year is not None else "",
                "author": author,
                "title": title,
                "url": url,
                "status": status,
            })
            print(f"[{index}/{len(all_ids)}] {status}: {record_id}")
        except ServerRejectedRequest as exc:
            rows.append({"record_id": record_id, "year": "", "author": "", "title": "", "url": url, "status": f"server_rejected: {exc}"})
            print(f"[{index}/{len(all_ids)}] stopped: {record_id}: {exc}")
            server_blocked = True
            break
        except (urllib.error.URLError, ET.ParseError, ValueError, TimeoutError) as exc:
            rows.append({"record_id": record_id, "year": "", "author": "", "title": "", "url": url, "status": f"error: {exc}"})
            print(f"[{index}/{len(all_ids)}] error: {record_id}: {exc}")
        if index < len(all_ids):
            time.sleep(max(0.0, args.delay))

    manifest = args.output / "manifest.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("record_id", "year", "author", "title", "url", "status"))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved manifest: {manifest}")
    return 2 if server_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
