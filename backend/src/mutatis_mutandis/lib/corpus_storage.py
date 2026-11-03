"""
corpus_storage.py  (place alongside corpus_config.py in mutatis_mutandis/lib/)

Workstation <-> Colab transfer layer. One switch selects the backend:

    PASSAGES_STORAGE=drive   (default) read/write the mapped Google Drive folder
    PASSAGES_STORAGE=hf      stage locally, sync with a private Hugging Face dataset repo

Environment variables (hf backend):
    PASSAGES_HF_REPO         dataset repo id, e.g. "youruser/albinism-passages"  (required)
    PASSAGES_STAGING_DIR     local staging folder (default: ~/passages_hf_staging)
    HF_TOKEN                 write-enabled token, or run `hf auth login` once

Repo layout (identical to the Drive layout):
    source_tokens/tokens_*.parquet        workstation -> Colab
    output-passages/passages_*.parquet    Colab -> workstation

Usage:
    out = local_dir("source_tokens")   # where to write shards
    clear("source_tokens", "tokens_*.parquet")   # drop shards from a previous batch
    ...write files...
    publish("source_tokens", "tokens_*.parquet", prune=True)  # no-op on Drive; uploads on hf
    warn_stale_outputs()               # old embeddings would make Colab skip new shards

    inp = fetch("output-passages")     # Drive path, or downloads from hf first

Manual reset of derived data (embeddings + checkpoints), from the project root:
    python -m mutatis_mutandis.lib.corpus_storage reset-outputs
"""
import argparse
import os
import shutil
from pathlib import Path

from mutatis_mutandis.lib.corpus_config import MAPPED_GOOGLE_DRIVE
from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger(__name__)

BACKEND = os.environ.get("PASSAGES_STORAGE", "drive").strip().lower()
HF_REPO_ID = os.environ.get("PASSAGES_HF_REPO", "").strip()
STAGING_DIR = Path(
    os.environ.get("PASSAGES_STAGING_DIR", Path.home() / "passages_hf_staging")
)

if BACKEND not in {"drive", "hf"}:
    raise ValueError(f"PASSAGES_STORAGE must be 'drive' or 'hf', not {BACKEND!r}")


def _repo() -> str:
    if not HF_REPO_ID:
        raise SystemExit(
            "PASSAGES_STORAGE=hf requires PASSAGES_HF_REPO (e.g. 'youruser/albinism-passages')"
        )
    return HF_REPO_ID


def local_dir(subdir: str) -> Path:
    """Directory the exporters write into (created if missing)."""
    root = Path(MAPPED_GOOGLE_DRIVE) if BACKEND == "drive" else STAGING_DIR
    path = root / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear(subdir: str, pattern: str = "*.parquet") -> int:
    """
    Delete files matching pattern directly inside local_dir(subdir): the Drive
    folder or the staging folder, depending on backend. Returns the count.
    Does not recurse and never touches other file types.
    """
    count = 0
    for path in local_dir(subdir).glob(pattern):
        if path.is_file():
            path.unlink()
            count += 1
    logger.info("Cleared %d local file(s) matching %s/%s", count, subdir, pattern)
    return count


def clear_remote(subdir: str, pattern: str = "*.parquet") -> None:
    """Delete matching files from the Hugging Face repo (no-op on Drive)."""
    if BACKEND == "drive":
        return

    from huggingface_hub import HfApi

    repo = _repo()
    try:
        HfApi().delete_files(
            repo_id=repo,
            repo_type="dataset",
            delete_patterns=[f"{subdir}/{pattern}"],
            commit_message=f"Delete {subdir}/{pattern}",
        )
        logger.info("Deleted %s/%s from %s", subdir, pattern, repo)
    except Exception as exc:  # e.g. nothing matched
        logger.warning("Remote delete of %s/%s did nothing: %s", subdir, pattern, exc)


def reset_outputs() -> None:
    """
    Delete all derived data of the previous batch: passages_*.parquet and the
    _checkpoints/ tree, locally (Drive folder or staging) and, on the hf backend,
    in the repo. Lance indexes are not touched.
    """
    clear("output-passages", "passages_*.parquet")
    shutil.rmtree(local_dir("output-passages") / "_checkpoints", ignore_errors=True)
    clear_remote("output-passages", "passages_*.parquet")
    clear_remote("output-passages/_checkpoints", "*")   # '*' also matches nested paths
    logger.info("Previous embeddings and checkpoints removed")


def warn_stale_outputs() -> None:
    """
    Warn if embeddings or checkpoints from an earlier batch are still stored.
    The Colab job skips any shard whose passages_*.parquet exists and resumes from
    checkpoints, so after re-exporting tokens these would silently win.
    """
    try:
        if BACKEND == "drive":
            out = Path(MAPPED_GOOGLE_DRIVE) / "output-passages"
            found = [p.name for p in out.glob("passages_*.parquet")] if out.exists() else []
            ckpt = out / "_checkpoints"
            if ckpt.exists() and any(ckpt.iterdir()):
                found.append("_checkpoints/")
        else:
            from huggingface_hub import HfApi

            found = [
                f for f in HfApi().list_repo_files(_repo(), repo_type="dataset")
                if f.startswith(("output-passages/passages_", "output-passages/_checkpoints/"))
            ]
    except Exception as exc:
        logger.warning("Could not check for stale outputs: %s", exc)
        return

    if found:
        logger.warning(
            "%d existing output item(s) from an earlier batch (e.g. %s). Colab will SKIP "
            "shards that already have output. If this is a fresh batch, clear them with "
            "reset_outputs() (see the top of corpus_storage.py).",
            len(found), found[0],
        )


def publish(subdir: str, pattern: str = "*.parquet", prune: bool = False) -> None:
    """
    Push local_dir(subdir) to the backend. No-op on Drive (the app syncs it).
    prune=True also deletes remote files matching pattern that are not part of
    this upload, so the repo ends up identical to the local folder.
    """
    if BACKEND == "drive":
        return

    from huggingface_hub import HfApi

    repo = _repo()
    api = HfApi()
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)

    logger.info("Uploading %s/%s to Hugging Face repo %s", subdir, pattern, repo)
    # upload_folder replaces upload_large_folder (removed in huggingface_hub 2.0)
    # and handles large, resumable uploads. Unchanged files are skipped.
    api.upload_folder(
        repo_id=repo,
        repo_type="dataset",
        folder_path=str(STAGING_DIR / subdir),
        path_in_repo=subdir,
        allow_patterns=[pattern],
        delete_patterns=[pattern] if prune else None,
        commit_message=f"Upload {subdir}/{pattern}",
    )
    logger.info("Upload complete")


def fetch(subdir: str, pattern: str = "*.parquet") -> Path:
    """Return a local directory containing the backend's copy of subdir."""
    if BACKEND == "drive":
        return Path(MAPPED_GOOGLE_DRIVE) / subdir

    from huggingface_hub import snapshot_download

    repo = _repo()
    logger.info("Downloading %s/%s from Hugging Face repo %s", subdir, pattern, repo)
    snapshot_download(
        repo_id=repo,
        repo_type="dataset",
        local_dir=str(STAGING_DIR),
        allow_patterns=[f"{subdir}/{pattern}"],
    )
    return STAGING_DIR / subdir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maintenance for the passage pipeline storage.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clear", help="delete files matching SUBDIR/PATTERN")
    c.add_argument("subdir")
    c.add_argument("pattern", nargs="?", default="*.parquet")
    c.add_argument("--remote", action="store_true", help="also delete from Hugging Face (hf backend)")
    sub.add_parser("reset-outputs", help="delete embeddings and checkpoints, locally and remotely")
    args = parser.parse_args()

    if args.cmd == "reset-outputs":
        reset_outputs()
    else:
        clear(args.subdir, args.pattern)
        if args.remote:
            clear_remote(args.subdir, args.pattern)
