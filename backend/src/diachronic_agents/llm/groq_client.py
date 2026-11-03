from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tiktoken
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from mutatis_mutandis.lib.corpus_logging import get_logger
from mutatis_mutandis.lib.corpus_config import OUT_DIR

logger = get_logger(__name__)


CLASSIFIER_MODEL = "openai/gpt-oss-20b"

DEFAULT_CACHE_PATH = Path(
    OUT_DIR / "cache" / "passage_classifications.sqlite3"
)


FeatureType = Literal[
    "human_hair",
    "animal_fur",
    "feathers",
    "flaxen_hair",
    "complexion",
    "other",
    "uncertain",
]

ClassificationType = Literal[
    "relevant",
    "ambiguous",
    "irrelevant",
]


@dataclass
class ClassificationConfig:
    search_term: str
    target_description: str
    include: list[str]
    exclude: list[str]
    retain_ambiguous: bool = True


class PassageClassification(BaseModel):
    passage_id: str

    classification: ClassificationType = Field(
        description="Whether the passage is relevant to the research."
    )

    feature_type: FeatureType = Field(
        description=(
            "The kind of hair, bodily covering or complexion described."
        )
    )

    reason: str = Field(
        description="Brief explanation of the classification."
    )


class ClassificationResult(BaseModel):
    classifications: list[PassageClassification]


BODILY_COVERING_CONFIG = ClassificationConfig(
    search_term="white hair",
    target_description=(
        "Descriptions of unusually white or pale human hair, "
        "human complexion, or animal bodily coverings. "
        "Human hair and complexion are primary categories. "
        "Animal hair, fur, feathers and flaxen hair are "
        "retained as distinct secondary categories."
    ),
    include=[
        "Human hair, including scalp hair and facial hair",
        "Human complexion, including unusually pale complexion",
        "Animal hair, fur, coats and manes",
        "Feathers and plumage as animal bodily coverings",
        "Mythological, symbolic and allegorical animals",
        "Descriptions of hair or bodily-covering colour even when "
        "the creature is fictional",
        "Flaxen or similarly pale hair, recorded separately from white hair",
    ],
    exclude=[
        "White garments, clothing and robes",
        "White fabric, wool as a material, silk and textiles",
        "White paint, stone, buildings and other objects",
        "White light and radiance without a bodily description",
    ],
)


def create_researcher_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    return ChatGroq(
        model=CLASSIFIER_MODEL,
        temperature=0,
        max_retries=2,
        max_tokens=2048,
        model_kwargs={
            "response_format": {
                "type": "json_object"
            }
        },
    )


# ------------------------------------------------------------
# Cache
# ------------------------------------------------------------

def get_cache_path() -> Path:
    configured_path = os.getenv("PASSAGE_CLASSIFICATION_CACHE")

    if configured_path:
        return Path(configured_path).expanduser()

    return DEFAULT_CACHE_PATH


def initialise_cache(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS passage_classifications (
            cache_key TEXT PRIMARY KEY,
            classification TEXT NOT NULL,
            feature_type TEXT NOT NULL,
            reason TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_passage_classifications_model
        ON passage_classifications(model)
        """
    )

    connection.commit()


def make_cache_key(
    passage: dict,
    instructions: dict,
    system_prompt: str,
) -> str:
    """
    Generate a stable key for the complete classification input.

    The passage ID is deliberately excluded. Identical text and
    metadata can therefore reuse a classification across searches.
    """

    cache_input = {
        "model": CLASSIFIER_MODEL,
        "system_prompt": system_prompt,
        "configuration": instructions,
        "passage": {
            "pub_year": passage.get("pub_year"),
            "title": passage.get("title"),
            "author": passage.get("author"),
            "text": passage.get("text") or "",
        },
    }

    serialised = json.dumps(
        cache_input,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

    return hashlib.sha256(
        serialised.encode("utf-8")
    ).hexdigest()


def load_cached_classification(
    connection: sqlite3.Connection,
    cache_key: str,
) -> dict | None:

    row = connection.execute(
        """
        SELECT classification, feature_type, reason
        FROM passage_classifications
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


def save_cached_classification(
    connection: sqlite3.Connection,
    cache_key: str,
    item: PassageClassification,
) -> None:

    connection.execute(
        """
        INSERT OR REPLACE INTO passage_classifications (
            cache_key,
            classification,
            feature_type,
            reason,
            model
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            cache_key,
            item.classification,
            item.feature_type,
            item.reason,
            CLASSIFIER_MODEL,
        ),
    )


# ------------------------------------------------------------
# Classification
# ------------------------------------------------------------

def classify_passages(
    passages: list[dict],
    config: ClassificationConfig,
) -> ClassificationResult:

    if not passages:
        return ClassificationResult(classifications=[])

    llm = create_researcher_llm()

    # Conservative local request budget.
    MAX_ESTIMATED_TOKENS = 6500
    TOKEN_SAFETY_MULTIPLIER = 1.25
    TOKEN_OVERHEAD = 300

    encoding = tiktoken.get_encoding("o200k_base")

    system_prompt = """
Classify each historical passage using the supplied configuration.

Return one result for every passage.

classification:
- relevant
- ambiguous
- irrelevant

feature_type:
- human_hair
- animal_fur
- feathers
- flaxen_hair
- complexion
- other
- uncertain

Rules:
- Human hair and human complexion are primary categories.
- Animal hair and fur are secondary categories.
- Feathers and plumage are secondary and distinct from hair.
- Flaxen hair is secondary; do not automatically equate it with white.
- Complexion is a separate feature, not hair.
- Clothing, textiles, materials, objects and light are not bodily features.
- Classify what the passage actually describes.
- Do not infer historical influence or transmission.
- Use the exact passage IDs supplied.
- Keep reasons under 10 words.

Return only valid JSON:
{"classifications":[{"passage_id":"P001","classification":"relevant","feature_type":"human_hair","reason":"Describes white human scalp hair."}]}
"""

    instructions = {
        "search_term": config.search_term,
        "target_description": config.target_description,
        "include": config.include,
        "exclude": config.exclude,
        "retain_ambiguous": config.retain_ambiguous,
    }

    # --------------------------------------------------------
    # Open and initialise the persistent cache.
    # --------------------------------------------------------

    cache_path = get_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        cache_path,
        timeout=30,
    )

    try:
        initialise_cache(connection)

        logger.info(
            "Classification cache: %s",
            cache_path.resolve(),
        )

        # ----------------------------------------------------
        # Check each passage against the cache.
        # ----------------------------------------------------

        results_by_passage_id = {}
        uncached_passages = []

        cache_hits = 0

        for passage in passages:
            original_id = passage["id"]

            cache_key = make_cache_key(
                passage,
                instructions,
                system_prompt,
            )

            cached = load_cached_classification(
                connection,
                cache_key,
            )

            if cached is not None:
                results_by_passage_id[original_id] = (
                    PassageClassification(
                        passage_id=original_id,
                        **cached,
                    )
                )

                cache_hits += 1
                continue

            uncached_passages.append({
                "original_id": original_id,
                "cache_key": cache_key,
                "passage": passage,
            })

        logger.info(
            "Classification cache: %d hits, %d misses",
            cache_hits,
            len(uncached_passages),
        )

        if not uncached_passages:
            logger.info("All classifications served from cache")

            return ClassificationResult(
                classifications=[
                    results_by_passage_id[p["id"]]
                    for p in passages
                ]
            )

        # ----------------------------------------------------
        # Prepare only uncached passages for the LLM.
        # ----------------------------------------------------

        id_map = {}
        cache_key_map = {}
        prepared = []

        for index, record in enumerate(
            uncached_passages,
            start=1,
        ):
            short_id = f"P{index:03d}"

            id_map[short_id] = record["original_id"]
            cache_key_map[short_id] = record["cache_key"]

            passage = record["passage"]

            prepared.append({
                "passage_id": short_id,
                "pub_year": passage.get("pub_year"),
                "title": passage.get("title"),
                "author": passage.get("author"),
                "text": (passage.get("text") or "")[:500],
            })

        def make_messages(
            batch: list[dict],
        ) -> list[tuple[str, str]]:

            payload = {
                "configuration": instructions,
                "passages": batch,
            }

            return [
                ("system", system_prompt),
                (
                    "human",
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            ]

        def estimate_tokens(
            messages: list[tuple[str, str]],
        ) -> int:

            raw_tokens = sum(
                len(encoding.encode(content))
                for _, content in messages
            )

            return int(
                raw_tokens * TOKEN_SAFETY_MULTIPLIER
            ) + TOKEN_OVERHEAD

        def validate_result(
            result: ClassificationResult,
            expected_ids: set[str],
            description: str,
        ) -> set[str]:

            returned_ids = [
                item.passage_id
                for item in result.classifications
            ]

            counts = Counter(returned_ids)

            missing = expected_ids - set(returned_ids)
            unexpected = set(returned_ids) - expected_ids

            duplicates = {
                key: count
                for key, count in counts.items()
                if count > 1
            }

            if unexpected or duplicates:
                raise ValueError(
                    f"{description} ID validation failed:\n"
                    f"Unexpected: {sorted(unexpected)}\n"
                    f"Duplicates: {duplicates}"
                )

            return missing

        # ----------------------------------------------------
        # Greedily construct batches within the local budget.
        # ----------------------------------------------------

        batches = []
        current_batch = []

        for passage in prepared:
            candidate = current_batch + [passage]
            candidate_messages = make_messages(candidate)
            estimated = estimate_tokens(candidate_messages)

            if estimated <= MAX_ESTIMATED_TOKENS:
                current_batch = candidate
                continue

            if not current_batch:
                raise ValueError(
                    f"Passage {passage['passage_id']} alone exceeds "
                    f"the estimated request budget ({estimated} tokens)."
                )

            batches.append(current_batch)
            current_batch = [passage]

            estimated = estimate_tokens(
                make_messages(current_batch)
            )

            if estimated > MAX_ESTIMATED_TOKENS:
                raise ValueError(
                    f"Passage {passage['passage_id']} alone exceeds "
                    f"the estimated request budget ({estimated} tokens)."
                )

        if current_batch:
            batches.append(current_batch)

        logger.info(
            "LLM classification: %d uncached passages in %d batches",
            len(prepared),
            len(batches),
        )

        # ----------------------------------------------------
        # Process batches.
        # ----------------------------------------------------

        for batch_number, batch in enumerate(
            batches,
            start=1,
        ):
            messages = make_messages(batch)
            estimated = estimate_tokens(messages)

            if estimated > MAX_ESTIMATED_TOKENS:
                raise RuntimeError(
                    f"Refusing to send batch {batch_number}: "
                    f"estimated {estimated} tokens."
                )

            logger.info(
                "LLM batch %d/%d: %d passages, approximately %d tokens",
                batch_number,
                len(batches),
                len(batch),
                estimated,
            )

            try:
                response = llm.invoke(messages)
            except Exception:
                logger.exception(
                    "Groq classification failed for batch %d/%d",
                    batch_number,
                    len(batches),
                )
                raise

            result = ClassificationResult.model_validate(
                json.loads(response.content)
            )

            expected_ids = {
                p["passage_id"]
                for p in batch
            }

            missing = validate_result(
                result,
                expected_ids,
                f"Batch {batch_number}",
            )

            # -----------------------------------------------
            # Retry only omitted passages.
            # -----------------------------------------------

            if missing:
                logger.warning(
                    "Batch %d omitted %d passages: %s",
                    batch_number,
                    len(missing),
                    sorted(missing),
                )

                missing_passages = [
                    passage
                    for passage in batch
                    if passage["passage_id"] in missing
                ]

                retry_messages = make_messages(
                    missing_passages
                )

                retry_estimated = estimate_tokens(
                    retry_messages
                )

                if retry_estimated > MAX_ESTIMATED_TOKENS:
                    raise RuntimeError(
                        f"Retry for batch {batch_number} exceeds "
                        f"the estimated request budget."
                    )

                logger.info(
                    "Retrying %d omitted passages",
                    len(missing_passages),
                )

                retry_response = llm.invoke(retry_messages)

                retry_result = ClassificationResult.model_validate(
                    json.loads(retry_response.content)
                )

                retry_expected = {
                    passage["passage_id"]
                    for passage in missing_passages
                }

                retry_missing = validate_result(
                    retry_result,
                    retry_expected,
                    f"Batch {batch_number} retry",
                )

                if retry_missing:
                    raise ValueError(
                        f"Retry still omitted passages: "
                        f"{sorted(retry_missing)}"
                    )

                result.classifications.extend(
                    retry_result.classifications
                )

            # -----------------------------------------------
            # Cache validated classifications and restore IDs.
            # -----------------------------------------------

            for item in result.classifications:
                original_id = id_map[item.passage_id]
                cache_key = cache_key_map[item.passage_id]

                restored = PassageClassification(
                    passage_id=original_id,
                    classification=item.classification,
                    feature_type=item.feature_type,
                    reason=item.reason,
                )

                results_by_passage_id[original_id] = restored

                save_cached_classification(
                    connection,
                    cache_key,
                    item,
                )

            connection.commit()

        # ----------------------------------------------------
        # Return results in the same order as the input.
        # ----------------------------------------------------

        return ClassificationResult(
            classifications=[
                results_by_passage_id[p["id"]]
                for p in passages
            ]
        )

    finally:
        connection.close()
