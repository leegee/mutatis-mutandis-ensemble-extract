
#!/usr/bin/env python3
"""
Download selected Exeter Book poems from CLASP.

Default: TEI XML
Optional: plain text

Ranges:
    A.3.22.1 - A.3.22.59
    A.3.34.61 - A.3.34.95
"""

import argparse
import time
import urllib.error
import urllib.request
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import CORPUS_INPUT_DIRS

# BASE_URL = "https://clasp.ell.ox.ac.uk/db-latest/poem"

# POEM_RANGES = [
#     ("A.3.22", 1, 59),
#     ("A.3.34", 61, 95),
# ]

# def get_poem_ids():
#     for prefix, start, end in POEM_RANGES:
#         for number in range(start, end + 1):
#             yield f"{prefix}.{number}"


# def download(url, destination, retries=3):
#     for attempt in range(1, retries + 1):
#         try:
#             request = urllib.request.Request(
#                 url,
#                 headers={"User-Agent": "CLASP-Corpus-Downloader/1.0"},
#             )

#             with urllib.request.urlopen(request, timeout=30) as response:
#                 content = response.read()

#             if not content:
#                 raise ValueError("Empty response")

#             # Write atomically, so interrupted downloads don't leave
#             # apparently complete files.
#             temporary = destination.with_suffix(
#                 destination.suffix + ".tmp"
#             )
#             temporary.write_bytes(content)
#             temporary.replace(destination)

#             return True

#         except urllib.error.HTTPError as exc:
#             if exc.code == 404:
#                 print(f"  NOT FOUND: {url}")
#                 return False

#             print(f"  HTTP {exc.code}, attempt {attempt}/{retries}")

#         except Exception as exc:
#             print(f"  ERROR: {exc}, attempt {attempt}/{retries}")

#         if attempt < retries:
#             time.sleep(attempt * 2)

#     return False


# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument(
#         "--format",
#         choices=["xml", "txt"],
#         default="xml",
#         help="Download format (default: xml)",
#     )
#     parser.add_argument(
#         "--output",
#         type=Path,
#         default=CORPUS_INPUT_DIRS["clasp"],
#         help="Output directory",
#     )
#     parser.add_argument(
#         "--overwrite",
#         action="store_true",
#         help="Download files even if they already exist",
#     )

#     args = parser.parse_args()

#     args.output.mkdir(parents=True, exist_ok=True)

#     poem_ids = list(get_poem_ids())

#     downloaded = 0
#     skipped = 0
#     failed = []

#     print(f"Downloading {len(poem_ids)} CLASP poems")
#     print(f"Format: {args.format}")
#     print(f"Output: {args.output.resolve()}")
#     print()

#     for index, poem_id in enumerate(poem_ids, start=1):
#         filename = f"{poem_id}.{args.format}"
#         url = f"{BASE_URL}/{filename}"
#         destination = args.output / f"riddle_{filename}"

#         print(f"[{index}/{len(poem_ids)}] {poem_id}")

#         if destination.exists() and not args.overwrite:
#             print("  SKIPPED (already exists)")
#             skipped += 1
#             continue

#         if download(url, destination):
#             print(f"  OK ({destination.stat().st_size:,} bytes)")
#             downloaded += 1
#         else:
#             failed.append(poem_id)

#         time.sleep(0.25)

#     print("\nDOWNLOAD SUMMARY")
#     print(f"  Total:      {len(poem_ids)}")
#     print(f"  Downloaded: {downloaded}")
#     print(f"  Skipped:    {skipped}")
#     print(f"  Failed:     {len(failed)}")

#     if failed:
#         print("\nFailed poem IDs:")
#         for poem_id in failed:
#             print(f"  {poem_id}")


# if __name__ == "__main__":
#     main()

#!/usr/bin/env python3


# from pathlib import Path
# from lxml import etree


# NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# XPATH = (
#     ".//tei:teiHeader/tei:fileDesc/"
#     "tei:publicationStmt/tei:date"
# )
# TEI_NS = "http://www.tei-c.org/ns/1.0"
# NS = {"tei": TEI_NS}
# for path in CORPUS_INPUT_DIRS["clasp"].glob("*.xml"):
#     try:
#         tree = etree.parse(str(path))
#         root = tree.getroot()

#         # Find fileDesc
#         file_desc = root.find(
#             ".//tei:teiHeader/tei:fileDesc",
#             namespaces=NS
#         )

#         if file_desc is None:
#             print(f"WARNING: No fileDesc: {path.name}")
#             continue

#         # Find or create publicationStmt
#         publication_stmt = file_desc.find(
#             "tei:publicationStmt",
#             namespaces=NS
#         )

#         if publication_stmt is None:
#             publication_stmt = etree.SubElement(
#                 file_desc,
#                 f"{{{TEI_NS}}}publicationStmt"
#             )
#             etree.SubElement(
#                 publication_stmt,
#                 f"{{{TEI_NS}}}p"
#             ).text = "Unpublished digital transcription"

#         # Find or create date
#         date = publication_stmt.find(
#             "tei:date",
#             namespaces=NS
#         )

#         if date is None:
#             date = etree.SubElement(
#                 publication_stmt,
#                 f"{{{TEI_NS}}}date"
#             )

#         date.text = "970"
#         date.set("when", "0970")

#         tree.write(
#             str(path),
#             encoding="UTF-8",
#             xml_declaration=True,
#             pretty_print=False
#         )

#         print(f"Updated: {path.name}")

#     except Exception as e:
#         print(f"ERROR: {path.name}: {e}")