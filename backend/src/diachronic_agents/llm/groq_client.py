from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import tiktoken
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from mutatis_mutandis.lib.corpus_logging import get_logger

from diachronic_agents.llm.passage_cache import ClassificationCache, make_cache_key

logger = get_logger(__name__)


CLASSIFIER_MODEL = "openai/gpt-oss-20b"

# Conservative local request budget.
MAX_ESTIMATED_TOKENS = 6500
TOKEN_SAFETY_MULTIPLIER = 1.25
TOKEN_OVERHEAD = 300

SYSTEM_PROMPT = """
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


# ------------------------------------------------------------
# Types and configuration
# ------------------------------------------------------------

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
        description="The kind of hair, bodily covering or complexion described."
    )

    reason: str = Field(
        description="Brief explanation of the classification."
    )


class ClassificationResult(BaseModel):
    classifications: list[PassageClassification]


@dataclass
class _CacheMiss:
    original_id: str
    cache_key: str
    passage: dict


BODILY_COVERING_CONFIG = ClassificationConfig(
    search_term="white hair",
    target_description=(
        "Descriptions of unusually white or pale human hair, "
        "human complexion, or animal bodily coverings. "
        "Human hair and complexion are primary categories. "
        "Animal hair, fur, feathers and flaxen hair are retained as distinct secondary categories."
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
        model_kwargs={"response_format": {"type": "json_object"}},
    )


# ------------------------------------------------------------
# Request construction and budgeting
# ------------------------------------------------------------

@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("o200k_base")


def _config_to_instructions(config: ClassificationConfig) -> dict:
    return {
        "search_term": config.search_term,
        "target_description": config.target_description,
        "include": config.include,
        "exclude": config.exclude,
        "retain_ambiguous": config.retain_ambiguous,
    }


def _make_messages(batch: list[dict], instructions: dict) -> list[tuple[str, str]]:
    payload = {"configuration": instructions, "passages": batch}
    return [
        ("system", SYSTEM_PROMPT),
        ("human", json.dumps(payload, ensure_ascii=False, default=str)),
    ]


def _estimate_tokens(batch: list[dict], instructions: dict) -> int:
    encoding = _encoding()
    raw = sum(
        len(encoding.encode(content))
        for _, content in _make_messages(batch, instructions)
    )
    return int(raw * TOKEN_SAFETY_MULTIPLIER) + TOKEN_OVERHEAD


def _build_batches(prepared: list[dict], instructions: dict) -> list[list[dict]]:
    """Greedily pack passages into batches within the token budget."""
    batches: list[list[dict]] = []
    current: list[dict] = []

    for passage in prepared:
        candidate = current + [passage]
        if _estimate_tokens(candidate, instructions) <= MAX_ESTIMATED_TOKENS:
            current = candidate
            continue

        if current:
            batches.append(current)
        current = [passage]

        estimated = _estimate_tokens(current, instructions)
        if estimated > MAX_ESTIMATED_TOKENS:
            raise ValueError(
                f"Passage {passage['passage_id']} alone exceeds "
                f"the estimated request budget ({estimated} tokens)."
            )

    if current:
        batches.append(current)

    return batches


# ------------------------------------------------------------
# LLM calls
# ------------------------------------------------------------

def _validate_result(
    result: ClassificationResult,
    expected_ids: set[str],
    description: str,
) -> set[str]:
    """Raise on unexpected or duplicate IDs; return the missing IDs."""
    returned_ids = [item.passage_id for item in result.classifications]
    counts = Counter(returned_ids)

    unexpected = set(returned_ids) - expected_ids
    duplicates = {k: n for k, n in counts.items() if n > 1}

    if unexpected or duplicates:
        raise ValueError(
            f"{description} ID validation failed:\n"
            f"Unexpected: {sorted(unexpected)}\n"
            f"Duplicates: {duplicates}"
        )

    return expected_ids - set(returned_ids)


def _invoke_batch(
    llm,
    batch: list[dict],
    instructions: dict,
    description: str,
) -> tuple[list[PassageClassification], set[str]]:
    """Send one batch. Returns (classifications, missing_ids)."""
    estimated = _estimate_tokens(batch, instructions)
    if estimated > MAX_ESTIMATED_TOKENS:
        raise RuntimeError(
            f"Refusing to send {description}: estimated {estimated} tokens."
        )

    logger.info(
        "LLM %s: %d passages, approximately %d tokens",
        description, len(batch), estimated,
    )

    try:
        response = llm.invoke(_make_messages(batch, instructions))
    except Exception:
        logger.exception("Groq classification failed for %s", description)
        raise

    result = ClassificationResult.model_validate(json.loads(response.content))
    missing = _validate_result(
        result,
        {p["passage_id"] for p in batch},
        description,
    )
    return result.classifications, missing


def _classify_batch(
    llm,
    batch: list[dict],
    instructions: dict,
    description: str,
) -> list[PassageClassification]:
    """Classify a batch, retrying once for any omitted passages."""
    items, missing = _invoke_batch(llm, batch, instructions, description)

    if not missing:
        return items

    logger.warning(
        "%s omitted %d passages: %s",
        description, len(missing), sorted(missing),
    )

    retry_batch = [p for p in batch if p["passage_id"] in missing]
    retry_items, still_missing = _invoke_batch(
        llm, retry_batch, instructions, f"{description} retry",
    )

    if still_missing:
        raise ValueError(f"Retry still omitted passages: {sorted(still_missing)}")

    return items + retry_items


# ------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------

def _split_cached(
    passages: list[dict],
    cache: ClassificationCache,
    instructions: dict,
) -> tuple[dict[str, PassageClassification], list[_CacheMiss]]:
    hits: dict[str, PassageClassification] = {}
    misses: list[_CacheMiss] = []

    for passage in passages:
        original_id = passage["id"]
        cache_key = make_cache_key(
            model=CLASSIFIER_MODEL,
            system_prompt=SYSTEM_PROMPT,
            configuration=instructions,
            passage=passage,
        )

        cached = cache.get(cache_key)
        if cached is not None:
            hits[original_id] = PassageClassification(
                passage_id=original_id, **cached,
            )
        else:
            misses.append(_CacheMiss(original_id, cache_key, passage))

    return hits, misses


def _prepare_for_llm(
    misses: list[_CacheMiss],
) -> tuple[list[dict], dict[str, _CacheMiss]]:
    """Assign short IDs and trim passages to what the LLM sees."""
    prepared: list[dict] = []
    lookup: dict[str, _CacheMiss] = {}

    for index, miss in enumerate(misses, start=1):
        short_id = f"P{index:03d}"
        lookup[short_id] = miss
        prepared.append({
            "passage_id": short_id,
            "pub_year": miss.passage.get("pub_year"),
            "title": miss.passage.get("title"),
            "author": miss.passage.get("author"),
            "text": (miss.passage.get("text") or "")[:500],
        })

    return prepared, lookup


def _classify_misses(
    misses: list[_CacheMiss],
    instructions: dict,
    cache: ClassificationCache,
) -> dict[str, PassageClassification]:
    llm = create_researcher_llm()
    prepared, lookup = _prepare_for_llm(misses)
    batches = _build_batches(prepared, instructions)

    logger.info(
        "LLM classification: %d uncached passages in %d batches",
        len(prepared), len(batches),
    )

    results: dict[str, PassageClassification] = {}

    for number, batch in enumerate(batches, start=1):
        description = f"batch {number}/{len(batches)}"

        for item in _classify_batch(llm, batch, instructions, description):
            miss = lookup[item.passage_id]
            results[miss.original_id] = item.model_copy(
                update={"passage_id": miss.original_id}
            )

            cache.put(
                miss.cache_key,
                classification=item.classification,
                feature_type=item.feature_type,
                reason=item.reason,
            )

        cache.commit()

    return results


def classify_passages(
    passages: list[dict],
    config: ClassificationConfig,
) -> ClassificationResult:
    if not passages:
        return ClassificationResult(classifications=[])

    instructions = _config_to_instructions(config)

    with ClassificationCache(model=CLASSIFIER_MODEL) as cache:
        results, misses = _split_cached(passages, cache, instructions)

        logger.info(
            "Classification cache: %d hits, %d misses",
            len(results), len(misses),
        )

        if misses:
            results.update(_classify_misses(misses, instructions, cache))

    return ClassificationResult(
        classifications=[results[p["id"]] for p in passages]
    )
    