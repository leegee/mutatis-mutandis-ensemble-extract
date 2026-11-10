"""
passages_2_0_colab_embed_ensemble.py

Colab job: stand-alone token parquet shards -> multi-scale passage-vector
parquet shards. Storage is Google Drive or a private Hugging Face dataset repo,
selected by STORAGE below.

Hugging Face mode: needs a write-enabled token in Colab Secrets named HF_TOKEN
(with "Notebook access" switched on). Inputs are downloaded to local disk, per-
document checkpoints stay on local disk and are synced to the repo every
CHECKPOINT_SYNC_SECONDS (one commit per sync, not per document), and each finished
shard is uploaded as a single file. After a disconnect, re-running resumes from
the synced checkpoints and skips shards already in the repo.

Uses MacBERTh. Independent of PostgreSQL / LanceDB.

Changes vs previous word-window version
---------------------------------------
* PASSAGE_SCALES Character windows at three scales instead of fixed 40-word windows:
    local  : 40 chars / hop 20
    medium : 256 chars / hop 64
    broad  : 512 chars / hop 128
* Each window is encoded independently (full text → tokenizer → masked mean pool).
* Contiguous-run logic retained: passages never bridge gaps in token_idx.
* Output schema adds "scale", "char_start", "char_end".
* Over-length windows (>512 tokens) raise; no silent truncation.

For now, manually keep configuration synchronised with lib.corpus_config / lib.macberth.
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
from transformers import AutoModel, AutoTokenizer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESUME_FROM_DOC = 0
STOP_AFTER_DOC  = 9999

STORAGE = "hf"                              # "drive" or "hf"
HF_REPO_ID = "leegee23/albinism-passages"   # same dataset repo the workstation uses (hf only)
CHECKPOINT_SYNC_SECONDS = 600               # hf only: how often to push checkpoints

DRIVE_ROOT = Path("/content/drive/MyDrive/passage-pipeline")
WORK_ROOT = Path("/content/work")           # hf mode working copy (local disk)

_ROOT = DRIVE_ROOT if STORAGE == "drive" else WORK_ROOT
IN_DIR = _ROOT / "source_tokens"
OUT_DIR = _ROOT / "output-passages"
CHECKPOINT_DIR = OUT_DIR / "_checkpoints"
LOCAL_TMP = Path("/content/tmp")

MODEL_NAME = "emanjavacas/MacBERTh"
ASSEMBLE_FINAL_SHARD = True

BATCH_SIZE = 16
MAX_MODEL_TOKENS = 512
DIM = 768

LAYER_NAMES = ("l8", "last", "mean4")

# Character window sizes and hops. This is lib.corpus_config.PASSAGE_SCALES
PASSAGE_SCALES = {
    "local":  (40, 20),
    "medium": (256, 64),
    "broad":  (512, 128),
}


def log(message):
    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] {message}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Hugging Face transfer helpers (used only when STORAGE == "hf")
# ---------------------------------------------------------------------------

_hf_api = None
_remote_done = set()
_last_sync = 0.0


def hf_setup():
    """Authenticate, pull inputs + resumable checkpoints, list finished shards."""
    global _hf_api, _remote_done, _last_sync
    from google.colab import userdata
    from huggingface_hub import HfApi, snapshot_download

    token = userdata.get("HF_TOKEN")
    _hf_api = HfApi(token=token)
    _hf_api.create_repo(HF_REPO_ID, repo_type="dataset", private=True, exist_ok=True)

    log(f"Downloading inputs and checkpoints from {HF_REPO_ID}")
    snapshot_download(
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        token=token,
        local_dir=str(WORK_ROOT),
        allow_patterns=[
            "source_tokens/*.parquet",
            "output-passages/_checkpoints/**",
        ],
    )
    _remote_done = {
        Path(f).name
        for f in _hf_api.list_repo_files(HF_REPO_ID, repo_type="dataset")
        if f.startswith("output-passages/passages_") and f.endswith(".parquet")
    }
    log(f"{len(_remote_done)} finished shard(s) already in the repo")
    _last_sync = time.time()


def hf_publish_shard(final_path):
    _hf_api.upload_file(
        path_or_fileobj=str(final_path),
        path_in_repo=f"output-passages/{final_path.name}",
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        commit_message=f"Add {final_path.name}",
    )
    _remote_done.add(final_path.name)


def hf_sync_checkpoints(force=False):
    """Push new checkpoints in one commit, at most every CHECKPOINT_SYNC_SECONDS."""
    global _last_sync
    if STORAGE != "hf":
        return
    if not force and time.time() - _last_sync < CHECKPOINT_SYNC_SECONDS:
        return
    _last_sync = time.time()   # also on failure, so a broken sync is not retried every document
    if not any(CHECKPOINT_DIR.glob("*/doc_*.parquet")):
        return
    try:
        _hf_api.upload_folder(
            folder_path=str(CHECKPOINT_DIR),
            path_in_repo="output-passages/_checkpoints",
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            allow_patterns=["*/doc_*.parquet"],
            commit_message="Sync checkpoints",
        )
        log("Checkpoints synced to Hugging Face")
    except Exception as exc:
        log(f"WARNING: checkpoint sync failed (will retry later): {exc}")


def hf_drop_checkpoints(stem):
    """Remove a finished shard's checkpoints locally and from the repo."""
    shutil.rmtree(CHECKPOINT_DIR / stem, ignore_errors=True)
    try:
        _hf_api.delete_folder(
            path_in_repo=f"output-passages/_checkpoints/{stem}",
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            commit_message=f"Drop checkpoints for {stem}",
        )
    except Exception as exc:
        log(f"No remote checkpoints removed for {stem}: {exc}")


# ---------------------------------------------------------------------------
# Core multi-scale embedding logic
# ---------------------------------------------------------------------------

def reconstruct_document(tokens, token_idxs):
    """
    Reconstruct text from ordered source tokens.
    Returns:
        text
        token_offsets: [(char_start, char_end), ...]
    """
    parts = []
    offsets = []
    position = 0
    for token in tokens:
        token = str(token) if str(token).strip() else "."
        if parts:
            parts.append(" ")
            position += 1
        start = position
        parts.append(token)
        position += len(token)
        offsets.append((start, position))
    return "".join(parts), offsets


def make_char_windows(text, token_offsets, token_idxs, scale_name):
    """
    Generate character windows and retain source token boundaries.
    Character offsets refer to reconstructed text.
    token_start / token_end refer to original token_idx values.
    word_start / word_end are indices into the (run-local) token list.
    """
    window_size, hop = PASSAGE_SCALES[scale_name]
    text_length = len(text)
    if not text_length:
        return []

    if text_length <= window_size:
        starts = [0]
    else:
        last_start = text_length - window_size
        starts = list(range(0, last_start + 1, hop))
        if starts[-1] != last_start:
            starts.append(last_start)

    windows = []
    for char_start in starts:
        char_end = min(char_start + window_size, text_length)
        intersecting = [
            i
            for i, (start, end) in enumerate(token_offsets)
            if end > char_start and start < char_end
        ]
        if not intersecting:
            continue
        first = intersecting[0]
        last = intersecting[-1]
        windows.append({
            "scale": scale_name,
            "char_start": char_start,
            "char_end": char_end,
            "token_start": int(token_idxs[first]),
            "token_end": int(token_idxs[last]),
            "word_start": first,
            "word_end": last + 1,
            "text": text[char_start:char_end],
        })
    return windows


def pool_hidden(hidden, attention_mask):
    """Masked mean pooling over input tokens."""
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    summed = (hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1)
    return summed / counts


def encode_windows(window_texts, tok, model, device):
    """
    Encode complete windows independently.
    Returns one vector for each of: l8, last, mean4.
    Raises if any window exceeds MacBERTh's 512-token limit.
    """
    results = {name: [] for name in LAYER_NAMES}

    for batch_start in range(0, len(window_texts), BATCH_SIZE):
        batch_texts = window_texts[batch_start:batch_start + BATCH_SIZE]

        encoded = tok(
            batch_texts,
            padding=True,
            truncation=False,
            max_length=MAX_MODEL_TOKENS,
            return_tensors="pt",
        )
        lengths = encoded["attention_mask"].sum(dim=1)
        too_long = torch.where(lengths > MAX_MODEL_TOKENS)[0]
        if len(too_long):
            bad_index = int(too_long[0])
            actual_length = int(lengths[bad_index])
            raise ValueError(
                "Window exceeds MacBERTh's 512-token limit: "
                f"{actual_length} tokens; "
                f"batch item {bad_index}; "
                f"text={batch_texts[bad_index][:120]!r}"
            )

        encoded = {k: v.to(device) for k, v in encoded.items()}

        with torch.inference_mode():
            output = model(**encoded)

        hidden_states = output.hidden_states
        attention_mask = encoded["attention_mask"]

        l8 = pool_hidden(hidden_states[8], attention_mask)
        last = pool_hidden(hidden_states[-1], attention_mask)
        mean4_hidden = torch.stack(hidden_states[-4:], dim=0).mean(dim=0)
        mean4 = pool_hidden(mean4_hidden, attention_mask)

        results["l8"].extend(l8.cpu().numpy().astype(np.float32))
        results["last"].extend(last.cpu().numpy().astype(np.float32))
        results["mean4"].extend(mean4.cpu().numpy().astype(np.float32))

        del output, hidden_states, l8, last, mean4, mean4_hidden

    return results


def doc_passage_vectors(doc, tok, model, device):
    """
    Produce multi-scale, multi-layer vectors for one document.

    Expected keys:
        doc["tokens"], doc["token_idx"]
        (plus corpus / doc_id / pub_year for metadata)

    Passages never bridge gaps in the original token positions.
    """
    tokens = doc["tokens"]
    token_idxs = doc["token_idx"]

    if len(tokens) != len(token_idxs):
        raise ValueError(
            f"tokens and token_idx length mismatch: "
            f"{len(tokens)} != {len(token_idxs)}"
        )
    if not tokens:
        return []

    # Sort by source ordering key.
    ordered = sorted(zip(token_idxs, tokens), key=lambda item: item[0])
    token_idxs = [item[0] for item in ordered]
    tokens = [item[1] for item in ordered]

    # Split into contiguous runs so windows never bridge omitted sections.
    run_starts = [0]
    run_starts.extend(
        i for i in range(1, len(token_idxs))
        if token_idxs[i] != token_idxs[i - 1] + 1
    )
    run_ends = run_starts[1:] + [len(token_idxs)]

    all_windows = []

    for run_start, run_end in zip(run_starts, run_ends):
        run_tokens = tokens[run_start:run_end]
        run_idxs = token_idxs[run_start:run_end]
        if not run_tokens:
            continue

        text, token_offsets = reconstruct_document(run_tokens, run_idxs)

        for scale_name in PASSAGE_SCALES:
            windows = make_char_windows(
                text, token_offsets, run_idxs, scale_name
            )
            # Convert run-local word offsets to global offsets into the
            # exported token arrays.
            for w in windows:
                w["word_start"] += run_start
                w["word_end"] += run_start
            all_windows.extend(windows)

    if not all_windows:
        return []

    vectors = encode_windows(
        [w["text"] for w in all_windows], tok, model, device
    )

    rows = []
    for i, window in enumerate(all_windows):
        row = {
            "corpus": doc["corpus"],
            "doc_id": doc["doc_id"],
            "pub_year": doc["pub_year"],
            "scale": window["scale"],
            "char_start": window["char_start"],
            "char_end": window["char_end"],
            "word_start": window["word_start"],
            "word_end": window["word_end"],
            "token_start": window["token_start"],
            "token_end": window["token_end"],
        }
        for layer_name in LAYER_NAMES:
            row[f"vec_{layer_name}"] = vectors[layer_name][i]
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Parquet helpers & pipeline (unchanged structure)
# ---------------------------------------------------------------------------

def fixed_f16(arr):
    arr = np.ascontiguousarray(arr, dtype=np.float16)
    return pa.FixedSizeListArray.from_arrays(pa.array(arr.ravel()), DIM)


def document_table(doc, tok, model, device):
    """Create a Parquet table for one document."""
    rows = doc_passage_vectors(doc, tok, model, device)
    if not rows:
        return None

    n = len(rows)
    arrays = {
        "corpus": pa.array([r["corpus"] for r in rows]),
        "doc_id": pa.array([r["doc_id"] for r in rows]),
        "pub_year": pa.array([r["pub_year"] for r in rows], type=pa.int32()),
        "scale": pa.array([r["scale"] for r in rows]),
        "char_start": pa.array([r["char_start"] for r in rows], type=pa.int32()),
        "char_end": pa.array([r["char_end"] for r in rows], type=pa.int32()),
        "word_start": pa.array([r["word_start"] for r in rows], type=pa.int32()),
        "word_end": pa.array([r["word_end"] for r in rows], type=pa.int32()),
        "token_start": pa.array([r["token_start"] for r in rows], type=pa.int32()),
        "token_end": pa.array([r["token_end"] for r in rows], type=pa.int32()),
    }
    for name in LAYER_NAMES:
        vecs = np.stack([r[f"vec_{name}"] for r in rows])
        arrays[f"vec_{name}"] = fixed_f16(vecs)

    return pa.table(arrays)


def commit_file(local_path, final_path):
    """Copy under a temporary name, then publish the final name (atomic on Drive)."""
    final_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = final_path.with_name(final_path.name + ".part")
    if part_path.exists():
        part_path.unlink()
    shutil.copyfile(local_path, part_path)
    pq.ParquetFile(part_path).metadata          # validate
    os.replace(part_path, final_path)


def valid_checkpoint(path):
    """Trust only readable checkpoints with the expected schema."""
    try:
        pf = pq.ParquetFile(path)
        names = set(pf.schema_arrow.names)
        required = {
            "corpus", "doc_id", "pub_year",
            "scale",
            "char_start", "char_end",
            "word_start", "word_end",
            "token_start", "token_end",
            "vec_l8", "vec_last", "vec_mean4",
        }
        return pf.metadata.num_rows > 0 and required.issubset(names)
    except Exception:
        return False


def process_shard(in_path, tok, model, device):
    shard_name = in_path.name.replace("tokens_", "passages_")
    final_path = OUT_DIR / shard_name

    if STORAGE == "hf" and shard_name in _remote_done:
        log(f"Already in Hugging Face repo; skipping {shard_name}")
        return

    if final_path.exists():
        try:
            pq.ParquetFile(final_path).metadata
        except Exception:
            log(f"Existing final file is unreadable; rebuilding {shard_name}")
            final_path.unlink()
        else:
            if STORAGE == "hf":   # built earlier but never uploaded
                hf_publish_shard(final_path)
                final_path.unlink()
            log(f"Already complete; skipping {shard_name}")
            return

    shard_checkpoints = CHECKPOINT_DIR / in_path.stem
    shard_checkpoints.mkdir(parents=True, exist_ok=True)

    pf = pq.ParquetFile(in_path)
    total_docs = pf.metadata.num_rows
    log(f"Processing {in_path.name}: {total_docs} documents")

    doc_index = 0
    for batch in pf.iter_batches(batch_size=1):
        for doc in batch.to_pylist():
            checkpoint = shard_checkpoints / f"doc_{doc_index:08d}.parquet"
            current_index = doc_index
            doc_index += 1

            if current_index < RESUME_FROM_DOC or current_index > STOP_AFTER_DOC:
                continue

            if checkpoint.exists() and valid_checkpoint(checkpoint):
                if doc_index % 25 == 0:
                    log(f"Resume: document {doc_index}/{total_docs}")
                continue

            if checkpoint.exists():
                checkpoint.unlink()

            if not doc["tokens"]:
                continue

            log(
                f"Embedding document {doc_index}/{total_docs}: "
                f"{doc['doc_id']}"
            )
            t0 = time.perf_counter()

            table = document_table(doc, tok, model, device)
            if table is None:
                continue

            local = LOCAL_TMP / checkpoint.name
            pq.write_table(table, local, compression="zstd")
            commit_file(local, checkpoint)
            local.unlink(missing_ok=True)
            hf_sync_checkpoints()

            log(
                f"Committed {doc['doc_id']}: {table.num_rows} passages "
                f"in {time.perf_counter() - t0:.1f}s"
            )
            del table

            if device == "cuda":
                torch.cuda.empty_cache()

    if doc_index != total_docs:
        raise RuntimeError(
            f"Document count mismatch: read {doc_index}, expected {total_docs}"
        )

    if not ASSEMBLE_FINAL_SHARD:
        hf_sync_checkpoints(force=True)
        print(
            f"CHECKPOINTS ONLY: {in_path.name}; "
            "skipping final-shard assembly."
        )
        return

    local_final = LOCAL_TMP / shard_name
    if local_final.exists():
        local_final.unlink()

    writer = None
    expected_rows = 0
    try:
        for checkpoint in sorted(shard_checkpoints.glob("doc_*.parquet")):
            if not valid_checkpoint(checkpoint):
                raise RuntimeError(f"Invalid checkpoint: {checkpoint}")
            table = pq.read_table(checkpoint)
            if writer is None:
                writer = pq.ParquetWriter(
                    local_final, table.schema, compression="zstd"
                )
            elif not table.schema.equals(writer.schema, check_metadata=False):
                raise RuntimeError(
                    f"Schema mismatch in checkpoint {checkpoint.name}"
                )
            writer.write_table(table)
            expected_rows += table.num_rows
            del table
    finally:
        if writer is not None:
            writer.close()

    if expected_rows == 0:
        raise RuntimeError(
            "No passage rows were produced; refusing to publish an empty shard"
        )

    assembled = pq.ParquetFile(local_final)
    if assembled.metadata.num_rows != expected_rows:
        raise RuntimeError("Final row-count validation failed")

    commit_file(local_final, final_path)
    local_final.unlink(missing_ok=True)

    if STORAGE == "hf":
        hf_publish_shard(final_path)
        final_path.unlink(missing_ok=True)      # free local disk
        hf_drop_checkpoints(in_path.stem)

    log(
        f"COMPLETE {shard_name}: {expected_rows} passages "
        f"from {total_docs} documents"
    )


def main():
    if STORAGE == "drive":
        from google.colab import drive
        drive.mount("/content/drive")
    elif STORAGE == "hf":
        hf_setup()
    else:
        raise SystemExit(f"STORAGE must be 'drive' or 'hf', not {STORAGE!r}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_TMP.mkdir(parents=True, exist_ok=True)

    shards = sorted(IN_DIR.glob("tokens_*.parquet"))
    log(f"Found {len(shards)} input shards in {IN_DIR}")
    if not shards:
        raise SystemExit("No tokens_*.parquet files found")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"Device: {device}")
    if device == "cpu":
        log("WARNING: CPU inference will be slow")

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(
        MODEL_NAME, output_hidden_states=True
    ).to(device).eval()

    if device == "cuda":
        model = model.half()

    log("Model ready")

    for i, in_path in enumerate(shards, 1):
        log(f"Shard {i}/{len(shards)}")
        process_shard(in_path, tok, model, device)

    log("Done")


if __name__ == "__main__":
    main()
