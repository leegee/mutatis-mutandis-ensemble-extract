from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger(__name__)

DEFAULT_CACHE_PATH = OUT_DIR / "cache" / "passage_classifications.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS classifications (
    cache_key TEXT PRIMARY KEY,
    classification TEXT NOT NULL,
    feature_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_classifications_model
    ON classifications(model);
"""


def get_cache_path() -> Path:
    configured = os.getenv("PASSAGE_CLASSIFICATION_CACHE")
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_PATH


def make_cache_key(
    *,
    model: str,
    system_prompt: str,
    configuration: dict,
    passage: dict,
) -> str:
    """Stable hash of everything that influences a classification.

    `passage` is the exact view the LLM sees (minus the passage ID), so
    identical text and metadata reuse a classification across searches.
    """
    payload = {
        "model": model,
        "system_prompt": system_prompt,
        "configuration": configuration,
        "passage": passage,
    }
    serialised = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


class ClassificationCache:
    """SQLite-backed cache of passage classifications."""

    def __init__(self, path: Path | None = None, *, model: str):
        self.path = path or get_cache_path()
        self.model = model
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=30)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("Classification cache: %s", self.path.resolve())

    def __enter__(self) -> "ClassificationCache":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def get(self, cache_key: str) -> dict | None:
        row = self._conn.execute(
            """
            SELECT classification, feature_type, reason
            FROM classifications
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()

        if row is None:
            return None

        return {
            "classification": row[0],
            "feature_type": row[1],
            "reason": row[2],
        }

    def put(
        self,
        cache_key: str,
        *,
        classification: str,
        feature_type: str,
        reason: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO classifications
                (cache_key, classification, feature_type, reason, model)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cache_key, classification, feature_type, reason, self.model),
        )

    def commit(self) -> None:
        self._conn.commit()
