
"""
lib/macberth.py

Minimal MacBERTh passage-query encoder extracted from the experimental module in mutatis main branch.

Public API:
    PASSAGE_REPRESENTATIONS
    encode_passage_query
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM


PASSAGE_CHUNK = 510
PASSAGE_OVERLAP = 96
PASSAGE_BATCH_SIZE = 32

PASSAGE_REPRESENTATIONS = ("l8", "last", "mean4")

_THIS_DIR = Path(__file__).resolve().parent.parent.parent
MACBERTH_MODEL_PATH = _THIS_DIR / "lib" / "macberth-huggingface"

_PYTORCH_MODEL = None
_PYTORCH_MODEL_LOCK = threading.Lock()


class MacberthModel:
    """Minimal wrapper around the PyTorch MacBERTh model."""

    def __init__(self, tokenizer, model, device: str):
        self.tokenizer = tokenizer
        self.model = model
        self.device = device

    @property
    def hidden_size(self) -> int:
        return self.model.config.hidden_size

    def encode(self, **kwargs):
        return self.model.base_model(**kwargs)


def _load_macberth() -> MacberthModel:
    if not MACBERTH_MODEL_PATH.is_dir():
        raise FileNotFoundError(
            f"MacBERTh model directory does not exist: "
            f"{MACBERTH_MODEL_PATH}"
        )

    tokenizer = AutoTokenizer.from_pretrained(
        MACBERTH_MODEL_PATH,
        local_files_only=True,
    )

    if not tokenizer.is_fast:
        raise RuntimeError("Tokenizer must be fast")

    model = AutoModelForMaskedLM.from_pretrained(
        MACBERTH_MODEL_PATH,
        local_files_only=True,
    )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    return MacberthModel(tokenizer, model, device)


def _get_macberth() -> MacberthModel:
    """Load the model once per process, on first use."""
    global _PYTORCH_MODEL

    if _PYTORCH_MODEL is None:
        with _PYTORCH_MODEL_LOCK:
            if _PYTORCH_MODEL is None:
                _PYTORCH_MODEL = _load_macberth()

    return _PYTORCH_MODEL


def _passage_layers(hidden_states):
    """Select the same layer representations as the indexing pipeline."""
    return {
        "l8": hidden_states[8],
        "last": hidden_states[-1],
        "mean4": torch.stack(hidden_states[-4:]).mean(0),
    }


@torch.inference_mode()
def _encode_passage_words(
    words: list[str],
    macberth: MacberthModel,
) -> dict[str, np.ndarray]:
    """Encode words contextually, preserving chunk overlap and pooling."""

    if not words:
        raise ValueError("Cannot encode an empty passage.")

    words = [word if word.strip() else "." for word in words]

    tokenizer = macberth.tokenizer
    device = macberth.device
    dim = macberth.hidden_size

    encoded = tokenizer(
        words,
        is_split_into_words=True,
        add_special_tokens=False,
        truncation=False,
    )

    input_ids = encoded["input_ids"]
    word_ids = np.asarray(encoded.word_ids())

    if len(input_ids) == 0:
        raise ValueError("Tokenizer produced no subword tokens.")

    chunks = []
    start = 0

    while True:
        end = min(start + PASSAGE_CHUNK, len(input_ids))
        chunks.append((start, end))

        if end == len(input_ids):
            break

        start = end - PASSAGE_OVERLAP

    sums = {
        name: np.zeros((len(words), dim), dtype=np.float32)
        for name in PASSAGE_REPRESENTATIONS
    }
    counts = np.zeros(len(words), dtype=np.float32)

    # Preserve the indexing pipeline's chunk processing order.
    order = sorted(
        range(len(chunks)),
        key=lambda i: chunks[i][1] - chunks[i][0],
    )

    for offset in range(0, len(order), PASSAGE_BATCH_SIZE):
        selected = [
            chunks[i]
            for i in order[offset:offset + PASSAGE_BATCH_SIZE]
        ]

        maxlen = max(end - start for start, end in selected) + 2

        input_batch = torch.full(
            (len(selected), maxlen),
            tokenizer.pad_token_id,
            dtype=torch.long,
        )
        attention_batch = torch.zeros(
            (len(selected), maxlen),
            dtype=torch.long,
        )

        for row, (start, end) in enumerate(selected):
            sequence = (
                [tokenizer.cls_token_id]
                + input_ids[start:end]
                + [tokenizer.sep_token_id]
            )
            input_batch[row, :len(sequence)] = torch.tensor(sequence)
            attention_batch[row, :len(sequence)] = 1

        output = macberth.encode(
            input_ids=input_batch.to(device),
            attention_mask=attention_batch.to(device),
            output_hidden_states=True,
        )

        layers = {
            name: tensor.float().cpu().numpy()
            for name, tensor in _passage_layers(
                output.hidden_states
            ).items()
        }

        for row, (start, end) in enumerate(selected):
            chunk_word_ids = word_ids[start:end]

            first = np.flatnonzero(
                np.r_[
                    True,
                    chunk_word_ids[1:] != chunk_word_ids[:-1],
                ]
            )

            unique_words = chunk_word_ids[first]
            sizes = np.diff(
                np.r_[first, len(chunk_word_ids)]
            ).astype(np.float32)

            counts[unique_words] += sizes

            for name in PASSAGE_REPRESENTATIONS:
                hidden = layers[name][row, 1:1 + end - start]
                sums[name][unique_words] += np.add.reduceat(
                    hidden,
                    first,
                    axis=0,
                )

    counts = np.maximum(counts, 1.0)[:, None]

    return {
        name: sums[name] / counts
        for name in PASSAGE_REPRESENTATIONS
    }


def encode_passage_query(
    text: str,
    representation: str,
    macberth: Optional[MacberthModel] = None,
) -> np.ndarray:
    """
    Encode a text query using the passage-indexing aggregation procedure.

    Returns an unnormalised float32 vector of shape (hidden_size,).
    Loads the cached PyTorch model if macberth is omitted.
    """

    if representation not in PASSAGE_REPRESENTATIONS:
        raise ValueError(
            f"Unknown representation {representation!r}; "
            f"choose from {PASSAGE_REPRESENTATIONS}"
        )

    words = text.split()
    if not words:
        raise ValueError("Query must contain at least one word.")

    macberth = macberth or _get_macberth()

    word_vectors = _encode_passage_words(words, macberth)
    vector = np.asarray(
        word_vectors[representation].mean(axis=0),
        dtype=np.float32,
    )

    if not np.isfinite(vector).all():
        raise ValueError("Query embedding contains non-finite values.")

    if np.linalg.norm(vector) < 1e-12:
        raise ValueError("Query embedding is a zero vector.")

    return vector
