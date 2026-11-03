# diachronic_agents/llm/passage_classifier.py

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
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
MAX_ESTIMATED_TOKENS = 6500
MAX_PASSAGES_PER_BATCH = 10

RESERVED_CATEGORIES = {
    "other": "Relevant, but fits none of the listed categories.",
    "uncertain": "The feature_type cannot be determined from the passage.",
}

SYSTEM_PROMPT = """
You classify passages from a historical corpus for a research query.

The configuration describes the query:
- search_term: the term being researched
- target_description: what counts as a match
- include / exclude: further guidance on what to keep or reject
- categories: the permitted feature_type names, each with a description
- rules: additional rules specific to this query

For every passage, return:
- classification: "relevant", "ambiguous" or "irrelevant"
  - relevant: the passage clearly meets the target description
  - ambiguous: it might meet it, but the passage is insufficient to decide
  - irrelevant: it matches an exclusion or does not address the target
- feature_type: exactly one name from configuration.categories
- reason: under 10 words

General rules:
- Classify what the passage actually says, not what it might imply.
- Do not infer historical influence, causation or transmission.
- Follow every entry in configuration.rules.
- Return one result for every passage.
- Use the exact passage IDs supplied.

Return only valid JSON in this shape:
{"classifications":[{"passage_id":"P001","classification":"relevant","feature_type":"<feature_type name>","reason":"<short reason>"}]}
"""


# ------------------------------------------------------------
# Types and configuration
# ------------------------------------------------------------

ClassificationType = Literal["relevant", "ambiguous", "irrelevant"]


@dataclass
class ClassificationConfig:
    """Describes one research query. Contains all subject-specific content."""

    search_term: str
    target_description: str
    include: list[str]
    exclude: list[str]
    categories: dict[str, str]
    rules: list[str] = field(default_factory=list)
    retain_ambiguous: bool = True  # for downstream filtering; not sent to the LLM
    max_passage_chars: int = 500
    metadata_fields: tuple[str, ...] = ("pub_year", "title", "author")

    def __post_init__(self) -> None:
        clash = set(self.categories) & set(RESERVED_CATEGORIES)
        if clash:
            raise ValueError(f"Categories use reserved names: {sorted(clash)}")


class PassageClassification(BaseModel):
    passage_id: str

    classification: ClassificationType = Field(
        description="Whether the passage is relevant to the research."
    )

    feature_type: str = Field(
        description="One of the feature_type names defined in the configuration."
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
    view: dict  # exactly what the LLM sees, minus the short ID


def create_researcher_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    return ChatGroq(
        model=CLASSIFIER_MODEL,
        temperature=0,
        max_retries=2,
        max_tokens=8192,
        reasoning_effort="low",
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
        "categories": {**config.categories, **RESERVED_CATEGORIES},
        "rules": config.rules,
    }


def _passage_view(passage: dict, config: ClassificationConfig) -> dict:
    """The part of a passage the LLM sees. Also the basis of the cache key."""
    view = {name: passage.get(name) for name in config.metadata_fields}
    view["text"] = (passage.get("text") or "")[: config.max_passage_chars]
    return view


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
        if (
            len(candidate) <= MAX_PASSAGES_PER_BATCH
            and _estimate_tokens(candidate, instructions) <= MAX_ESTIMATED_TOKENS
        ):
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


def _check_feature_type(
    item: PassageClassification,
    allowed: set[str],
) -> PassageClassification:
    """Replace a feature_type the config doesn't define with 'uncertain'."""
    if item.feature_type in allowed:
        return item

    logger.warning(
        "Passage %s returned unknown feature_type %r; using 'uncertain'",
        item.passage_id, item.feature_type,
    )
    return item.model_copy(update={"feature_type": "uncertain"})


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
        logger.exception("\nGroq classification failed for %s", description)
        logger.error("\ninstructions =")
        logger.error(instructions)
        raise

    result = ClassificationResult.model_validate(json.loads(response.content))
    missing = _validate_result(
        result,
        {p["passage_id"] for p in batch},
        description,
    )

    allowed = set(instructions["categories"])
    items = [_check_feature_type(item, allowed) for item in result.classifications]
    return items, missing


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
    config: ClassificationConfig,
    instructions: dict,
) -> tuple[dict[str, PassageClassification], list[_CacheMiss]]:
    hits: dict[str, PassageClassification] = {}
    misses: list[_CacheMiss] = []

    for passage in passages:
        original_id = passage["id"]
        view = _passage_view(passage, config)

        cache_key = make_cache_key(
            model=CLASSIFIER_MODEL,
            system_prompt=SYSTEM_PROMPT,
            configuration=instructions,
            passage=view,
        )

        cached = cache.get(cache_key)
        if cached is not None:
            hits[original_id] = PassageClassification(
                passage_id=original_id, **cached,
            )
        else:
            misses.append(_CacheMiss(original_id, cache_key, view))

    return hits, misses


def _prepare_for_llm(
    misses: list[_CacheMiss],
) -> tuple[list[dict], dict[str, _CacheMiss]]:
    """Assign short IDs to the uncached passages."""
    prepared: list[dict] = []
    lookup: dict[str, _CacheMiss] = {}

    for index, miss in enumerate(misses, start=1):
        short_id = f"P{index:03d}"
        lookup[short_id] = miss
        prepared.append({"passage_id": short_id, **miss.view})

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
        results, misses = _split_cached(passages, cache, config, instructions)

        logger.info(
            "Classification cache: %d hits, %d misses",
            len(results), len(misses),
        )

        if misses:
            results.update(_classify_misses(misses, instructions, cache))

    return ClassificationResult(
        classifications=[results[p["id"]] for p in passages]
    )
