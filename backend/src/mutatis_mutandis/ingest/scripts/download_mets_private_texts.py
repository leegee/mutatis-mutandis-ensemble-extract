#!/usr/bin/env python3
"""Download XML files from selected METS edition repositories.

This one-off downloader targets only the METS repositories for the Jesus
College MS 29 anthology and the Digby Mary Magdalene Play. It downloads the
current default branch archives from GitHub, extracts XML files, and writes a
CSV manifest. No third-party Python packages are required.

Usage:
    python download_mets_private_texts.py --output G:/corpus/mets_private
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

OWNER = "mets-editions"
REPOSITORIES = (
    "fein-owl",
    "coletti-digbymagdalene",
)
USER_AGENT = "METS-private-research-downloader/1.0"


def get_bytes(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def safe_relative_path(name: str) -> PurePosixPath | None:
    """Remove the archive's top directory and reject unsafe archive paths."""
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or name.startswith("/") or ".." in parts:
        return None
    return PurePosixPath(*parts[1:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Folder for downloaded XML and manifest.csv")
    parser.add_argument("--overwrite", action="store_true", help="Replace XML files already present")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds")
    parser.add_argument("--delay", type=float, default=1.0, help="Pause between repository downloads")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str | int]] = []

    for repo_index, repo in enumerate(REPOSITORIES, start=1):
        api_url = f"https://api.github.com/repos/{OWNER}/{repo}"
        try:
            metadata = json.loads(get_bytes(api_url, args.timeout))
            branch = metadata["default_branch"]
            archive_url = f"https://codeload.github.com/{OWNER}/{repo}/zip/refs/heads/{branch}"
            archive_data = get_bytes(archive_url, args.timeout)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            print(f"[{repo_index}/{len(REPOSITORIES)}] FAILED {repo}: {exc}")
            continue

        extracted = 0
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            for item in archive.infolist():
                relative = safe_relative_path(item.filename)
                if relative is None or item.is_dir() or relative.suffix.lower() != ".xml":
                    continue
                destination = args.output / repo / Path(*relative.parts)
                if destination.exists() and not args.overwrite:
                    print(f"  SKIP existing: {destination}")
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(item)
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(destination)
                manifest.append({
                    "repository": repo,
                    "branch": branch,
                    "source_path": item.filename,
                    "output_path": str(destination),
                    "bytes": len(data),
                    "repository_url": f"https://github.com/{OWNER}/{repo}",
                })
                extracted += 1

        print(f"[{repo_index}/{len(REPOSITORIES)}] {repo}: extracted {extracted} XML file(s)")
        if repo_index < len(REPOSITORIES):
            time.sleep(max(0.0, args.delay))

    manifest_path = args.output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ("repository", "branch", "source_path", "output_path", "bytes", "repository_url")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
