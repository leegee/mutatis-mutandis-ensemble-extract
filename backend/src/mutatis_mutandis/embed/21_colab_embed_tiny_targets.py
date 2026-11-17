"""
21_colab_embed_tiny_targets.py

Colab job: hit-window parquet shards (11_export_target_windows.py) ->
one row per hit occurrence, with six vectors:

    vec_target_{l8,last,mean4}   mean over the hit word's own sub-word tokens
    vec_context_{l8,last,mean4}  mean over every other word's sub-word tokens

Each hit is encoded once, centred on itself, with the same layers as
20_colab_embed_ensemble.py so the two sets are comparable. [CLS]/[SEP] are
excluded from both pools (the passage vectors in 20_ include them).

Storage works as in 20_: Drive, or a private Hugging Face dataset repo.
Outputs go to output-targets/, never to output-passages/.

Resuming: chunk checkpoints (CHUNK_HITS hits each) live on local disk and are
synced to the repo every CHECKPOINT_SYNC_SECONDS. Re-running skips shards
already in the repo and chunks already checkpointed.

Pilot: set SHARD_STRIDE (e.g. 20) to embed every 20th shard. Shards are ordered
by corpus/document, so a stride spreads the pilot across the corpus. A later full
run (stride 1) skips the shards already finished.

Context handling
----------------
* Context is the contiguous run of token_idx around the hit (never bridges gaps).
* If the run is over MAX_MODEL_TOKENS sub-words it is trimmed symmetrically
  around the hit (recorded in n_context_words); never silently truncated.
* Hits that cannot be embedded (no context, or no sub-words for the hit word)
  are counted in the summary and skipped.
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

STORAGE = "hf"                              # "drive" or "hf"
HF_REPO_ID = "leegee23/albinism-passages"
CHECKPOINT_SYNC_SECONDS = 600

SHARD_STRIDE = 1                            # pilot: 20 -> every 20th shard
MAX_SHARDS = None                           # or an int, to stop early

DRIVE_ROOT = Path("/content/drive/MyDrive/passage-pipeline")
WORK_ROOT = Path("/content/work")

_ROOT = DRIVE_ROOT if STORAGE == "drive" else WORK_ROOT
IN_DIR = _ROOT / "source_hits"
OUT_DIR = _ROOT / "output-targets"
CHECKPOINT_DIR = OUT_DIR / "_checkpoints"
LOCAL_TMP = Path("/content/tmp")

MODEL_NAME = "emanjavacas/MacBERTh"

CHUNK_HITS = 2_000
BATCH_SIZE = 32
MAX_MODEL_TOKENS = 512
DIM = 768
MIN_CONTEXT_WORDS = 2

LAYER_NAMES = ("l8", "last", "mean4")
ROLES = ("target", "context")
VECTOR_COLUMNS = tuple(f"vec_{role}_{layer}" for role in ROLES for layer in LAYER_NAMES)


def log(message):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


stats = {
    "embedded": 0,
    "resumed": 0,        # hits covered by a valid chunk checkpoint
    "skipped": 0,        # could not be embedded (see module docstring)
    "trimmed": 0,        # context trimmed to fit MAX_MODEL_TOKENS
    "skipped_shard": 0,  # hits in shards already complete
}


# ---------------------------------------------------------------------------
# Hugging Face transfer helpers (used only when STORAGE == "hf")
# ---------------------------------------------------------------------------

_hf_api = None
_remote_done = set()
_last_sync = 0.0


def hf_setup():
    global _hf_api, _remote_done, _last_sync
    from google.colab import userdata
    from huggingface_hub import HfApi, snapshot_download

    token = userdata.get("HF_TOKEN")
    _hf_api = HfApi(token=token)
    _hf_api.create_repo(HF_REPO_ID, repo_type="dataset", private=True, exist_ok=True)

    log(f"Downloading hit shards and checkpoints from {HF_REPO_ID}")
    snapshot_download(
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        token=token,
        local_dir=str(WORK_ROOT),
        allow_patterns=[
            "source_hits/*.parquet",
            "output-targets/_checkpoints/**",
        ],
    )
    _remote_done = {
        Path(f).name
        for f in _hf_api.list_repo_files(HF_REPO_ID, repo_type="dataset")
        if f.startswith("output-targets/targets_") and f.endswith(".parquet")
    }
    log(f"{len(_remote_done)} finished shard(s) already in the repo")
    _last_sync = time.time()


def hf_publish_shard(final_path):
    _hf_api.upload_file(
        path_or_fileobj=str(final_path),
        path_in_repo=f"output-targets/{final_path.name}",
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        commit_message=f"Add {final_path.name}",
    )
    _remote_done.add(final_path.name)


def hf_sync_checkpoints(force=False):
    global _last_sync
    if STORAGE != "hf":
        return
    if not force and time.time() - _last_sync < CHECKPOINT_SYNC_SECONDS:
        return
    _last_sync = time.time()
    if not any(CHECKPOINT_DIR.glob("*/chunk_*.parquet")):
        return
    try:
        _hf_api.upload_folder(
            folder_path=str(CHECKPOINT_DIR),
            path_in_repo="output-targets/_checkpoints",
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            allow_patterns=["*/chunk_*.parquet"],
            commit_message="Sync target checkpoints",
        )
        log("Checkpoints synced to Hugging Face")
    except Exception as exc:
        log(f"WARNING: checkpoint sync failed (will retry later): {exc}")


def hf_drop_checkpoints(stem):
    shutil.rmtree(CHECKPOINT_DIR / stem, ignore_errors=True)
    try:
        _hf_api.delete_folder(
            path_in_repo=f"output-targets/_checkpoints/{stem}",
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            commit_message=f"Drop checkpoints for {stem}",
        )
    except Exception as exc:
        log(f"No remote checkpoints removed for {stem}: {exc}")


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def normalise(token):
    """Same blank-token rule as 20_colab_embed_ensemble.reconstruct_document."""
    token = str(token)
    return token if token.strip() else "."


def contiguous_run(token_idxs, pos):
    """[lo, hi) of the run of consecutive token_idx values containing pos."""
    lo = pos
    while lo > 0 and token_idxs[lo - 1] + 1 == token_idxs[lo]:
        lo -= 1
    hi = pos + 1
    while hi < len(token_idxs) and token_idxs[hi - 1] + 1 == token_idxs[hi]:
        hi += 1
    return lo, hi


def encode_hit(hit, tok):
    """
    Tokenise one hit's context. Returns a dict with sub-word ids and the sub-word
    positions of the hit word ("target") and of all other words ("context"),
    or None if the hit cannot be embedded.
    """
    idxs = list(hit["token_idx"])
    toks = list(hit["tokens"])
    if len(idxs) != len(toks):
        raise ValueError(
            f"token_idx / tokens length mismatch for {hit['doc_id']}: "
            f"{len(idxs)} != {len(toks)}"
        )

    order = sorted(range(len(idxs)), key=idxs.__getitem__)
    idxs = [idxs[i] for i in order]
    words = [normalise(toks[i]) for i in order]

    try:
        pos = idxs.index(hit["hit_idx"])
    except ValueError:
        raise ValueError(f"hit {hit['hit_idx']} not in its context: {hit['doc_id']}")

    lo, hi = contiguous_run(idxs, pos)
    half = max(pos - lo, hi - 1 - pos)
    a, b = lo, hi
    trimmed = False

    while True:
        enc = tok(
            words[a:b],
            is_split_into_words=True,
            add_special_tokens=True,
            truncation=False,
        )
        ids = enc["input_ids"]
        if len(ids) <= MAX_MODEL_TOKENS:
            break
        if half == 0:
            raise ValueError(
                f"hit word alone exceeds {MAX_MODEL_TOKENS} sub-words: "
                f"{words[pos][:60]!r} in {hit['doc_id']}"
            )
        trimmed = True
        half = int(half * 0.8)
        a, b = max(lo, pos - half), min(hi, pos + half + 1)

    if b - a < MIN_CONTEXT_WORDS:
        return None

    word_ids = enc.word_ids()
    local_pos = pos - a
    target = [i for i, w in enumerate(word_ids) if w == local_pos]
    context = [i for i, w in enumerate(word_ids) if w is not None and w != local_pos]
    if not target or not context:
        return None

    if trimmed:
        stats["trimmed"] += 1

    return {
        "hit": hit,
        "ids": ids,
        "target": target,
        "context": context,
        "token_start": int(idxs[a]),
        "token_end": int(idxs[b - 1]),
        "n_context_words": b - a,
        "n_target_subwords": len(target),
    }


def embed_batch(items, model, device, pad_id):
    """Return {vec_<role>_<layer>: float32 array (n, DIM)} for a batch of encoded hits."""
    n = len(items)
    width = max(len(it["ids"]) for it in items)

    input_ids = torch.full((n, width), pad_id, dtype=torch.long)
    attention = torch.zeros((n, width), dtype=torch.long)
    target_mask = torch.zeros((n, width), dtype=torch.float32)
    context_mask = torch.zeros((n, width), dtype=torch.float32)

    for i, it in enumerate(items):
        length = len(it["ids"])
        input_ids[i, :length] = torch.tensor(it["ids"], dtype=torch.long)
        attention[i, :length] = 1
        target_mask[i, it["target"]] = 1.0
        context_mask[i, it["context"]] = 1.0

    with torch.inference_mode():
        output = model(
            input_ids=input_ids.to(device),
            attention_mask=attention.to(device),
        )

    hidden = output.hidden_states
    layers = {
        "l8": hidden[8],
        "last": hidden[-1],
        "mean4": torch.stack(hidden[-4:], dim=0).mean(dim=0),
    }

    masks = {
        "target": target_mask.to(device).unsqueeze(-1),
        "context": context_mask.to(device).unsqueeze(-1),
    }

    result = {}
    for layer_name, states in layers.items():
        states = states.float()           # pool in fp32 even when the model is fp16
        for role, mask in masks.items():
            pooled = (states * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            result[f"vec_{role}_{layer_name}"] = pooled.cpu().numpy()

    del output, hidden, layers
    return result


# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------

def fixed_f16(arr):
    arr = np.ascontiguousarray(arr, dtype=np.float16)
    return pa.FixedSizeListArray.from_arrays(pa.array(arr.ravel()), DIM)


def chunk_table(items, vectors):
    hits = [it["hit"] for it in items]
    arrays = {
        "corpus": pa.array([h["corpus"] for h in hits], type=pa.string()),
        "doc_id": pa.array([h["doc_id"] for h in hits], type=pa.string()),
        "pub_year": pa.array([h["pub_year"] for h in hits], type=pa.int32()),
        "hit_idx": pa.array([h["hit_idx"] for h in hits], type=pa.int32()),
        "matched_token": pa.array([h["matched_token"] for h in hits], type=pa.string()),
        "hit_groups": pa.array([list(h["hit_groups"]) for h in hits],
                               type=pa.list_(pa.string())),
        "routes": pa.array([list(h["routes"]) for h in hits],
                           type=pa.list_(pa.string())),
        "token_start": pa.array([it["token_start"] for it in items], type=pa.int32()),
        "token_end": pa.array([it["token_end"] for it in items], type=pa.int32()),
        "n_context_words": pa.array([it["n_context_words"] for it in items],
                                    type=pa.int32()),
        "n_target_subwords": pa.array([it["n_target_subwords"] for it in items],
                                      type=pa.int32()),
    }
    for name in VECTOR_COLUMNS:
        arrays[name] = fixed_f16(vectors[name])
    return pa.table(arrays)


def commit_file(local_path, final_path):
    """Copy under a temporary name, then publish the final name."""
    final_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = final_path.with_name(final_path.name + ".part")
    if part_path.exists():
        part_path.unlink()
    shutil.copyfile(local_path, part_path)
    pq.ParquetFile(part_path).metadata          # validate
    os.replace(part_path, final_path)


REQUIRED_COLUMNS = {
    "corpus", "doc_id", "pub_year", "hit_idx", "matched_token",
    "hit_groups", "routes", "token_start", "token_end",
    "n_context_words", "n_target_subwords",
    *VECTOR_COLUMNS,
}


def valid_checkpoint(path):
    try:
        pf = pq.ParquetFile(path)
        return pf.metadata.num_rows > 0 and REQUIRED_COLUMNS.issubset(pf.schema_arrow.names)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Shard processing
# ---------------------------------------------------------------------------

def embed_chunk(hits, tok, model, device):
    items = []
    for hit in hits:
        item = encode_hit(hit, tok)
        if item is None:
            stats["skipped"] += 1
        else:
            items.append(item)
    if not items:
        return None

    items.sort(key=lambda it: len(it["ids"]))   # tight padding

    parts = {name: [] for name in VECTOR_COLUMNS}
    for start in range(0, len(items), BATCH_SIZE):
        result = embed_batch(items[start:start + BATCH_SIZE], model, device, tok.pad_token_id)
        for name in VECTOR_COLUMNS:
            parts[name].append(result[name])

    vectors = {name: np.concatenate(parts[name]) for name in VECTOR_COLUMNS}
    return chunk_table(items, vectors)


def process_shard(in_path, tok, model, device):
    shard_name = in_path.name.replace("hits_", "targets_", 1)
    final_path = OUT_DIR / shard_name

    hits = pq.read_table(in_path).to_pylist()
    total = len(hits)

    if STORAGE == "hf" and shard_name in _remote_done:
        stats["skipped_shard"] += total
        log(f"Already in Hugging Face repo; skipping {shard_name}")
        return

    if final_path.exists():
        try:
            pq.ParquetFile(final_path).metadata
        except Exception:
            log(f"Existing final file is unreadable; rebuilding {shard_name}")
            final_path.unlink()
        else:
            if STORAGE == "hf":
                hf_publish_shard(final_path)
                final_path.unlink()
            stats["skipped_shard"] += total
            log(f"Already complete; skipping {shard_name}")
            return

    shard_checkpoints = CHECKPOINT_DIR / in_path.stem
    shard_checkpoints.mkdir(parents=True, exist_ok=True)
    log(f"Processing {in_path.name}: {total} hits")

    for chunk_no, start in enumerate(range(0, total, CHUNK_HITS)):
        chunk_hits = hits[start:start + CHUNK_HITS]
        checkpoint = shard_checkpoints / f"chunk_{chunk_no:05d}.parquet"

        if checkpoint.exists() and valid_checkpoint(checkpoint):
            stats["resumed"] += len(chunk_hits)
            continue
        if checkpoint.exists():
            checkpoint.unlink()

        t0 = time.perf_counter()
        table = embed_chunk(chunk_hits, tok, model, device)
        if table is None:
            log(f"{in_path.name} chunk {chunk_no}: nothing embeddable")
            continue

        stats["embedded"] += table.num_rows
        local = LOCAL_TMP / checkpoint.name
        pq.write_table(table, local, compression="zstd")
        commit_file(local, checkpoint)
        local.unlink(missing_ok=True)
        hf_sync_checkpoints()

        elapsed = time.perf_counter() - t0
        log(
            f"{in_path.name} chunk {chunk_no}: {table.num_rows}/{len(chunk_hits)} hits "
            f"in {elapsed:.1f}s ({table.num_rows / elapsed:.0f}/s)"
        )
        del table
        if device == "cuda":
            torch.cuda.empty_cache()

    # Assemble the shard from its chunk checkpoints.
    local_final = LOCAL_TMP / shard_name
    local_final.unlink(missing_ok=True)

    writer = None
    expected_rows = 0
    try:
        for checkpoint in sorted(shard_checkpoints.glob("chunk_*.parquet")):
            if not valid_checkpoint(checkpoint):
                raise RuntimeError(f"Invalid checkpoint: {checkpoint}")
            table = pq.read_table(checkpoint)
            if writer is None:
                writer = pq.ParquetWriter(local_final, table.schema, compression="zstd")
            elif not table.schema.equals(writer.schema, check_metadata=False):
                raise RuntimeError(f"Schema mismatch in checkpoint {checkpoint.name}")
            writer.write_table(table)
            expected_rows += table.num_rows
            del table
    finally:
        if writer is not None:
            writer.close()

    if expected_rows == 0:
        raise RuntimeError("No rows were produced; refusing to publish an empty shard")
    if pq.ParquetFile(local_final).metadata.num_rows != expected_rows:
        raise RuntimeError("Final row-count validation failed")

    commit_file(local_final, final_path)
    local_final.unlink(missing_ok=True)

    if STORAGE == "hf":
        hf_publish_shard(final_path)
        final_path.unlink(missing_ok=True)
        hf_drop_checkpoints(in_path.stem)

    log(f"COMPLETE {shard_name}: {expected_rows} occurrences from {total} hits")


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

    shards = sorted(IN_DIR.glob("hits_*.parquet"))
    log(f"Found {len(shards)} hit shards in {IN_DIR}")
    if not shards:
        raise SystemExit("No hits_*.parquet files found")
    shards = shards[::SHARD_STRIDE]
    if MAX_SHARDS:
        shards = shards[:MAX_SHARDS]
    log(f"Processing {len(shards)} shard(s) (stride {SHARD_STRIDE})")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log(f"Device: {device}")
    if device == "cpu":
        log("WARNING: CPU inference will be slow")

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    if not tok.is_fast:
        raise SystemExit("A fast tokenizer is required for word_ids() alignment")
    model = AutoModel.from_pretrained(
        MODEL_NAME, output_hidden_states=True
    ).to(device).eval()
    if device == "cuda":
        model = model.half()
    log("Model ready")

    for i, in_path in enumerate(shards, 1):
        log(f"Shard {i}/{len(shards)}")
        process_shard(in_path, tok, model, device)

    log(
        "Summary: "
        f"{stats['embedded']} embedded, {stats['resumed']} resumed from checkpoints, "
        f"{stats['skipped_shard']} in already-complete shards, "
        f"{stats['skipped']} skipped (unembeddable), "
        f"{stats['trimmed']} with trimmed context"
    )
    log("Done")


if __name__ == "__main__":
    main()
