
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from collections import Counter
from typing import Literal

import tiktoken
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from mutatis_mutandis.lib.corpus_logging import get_logger

logger = get_logger(__name__)


FeatureType = Literal[
    "human_hair",
    "animal_fur",
    "feathers",
    "flaxen_hair",
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
            "The kind of hair or bodily covering described."
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
        "Descriptions of unusually white or pale hair or bodily "
        "coverings. Human hair is the primary research category. "
        "Animal hair, fur, feathers and flaxen hair are retained "
        "as distinct secondary categories."
    ),
    include=[
        "Human hair, including scalp hair and facial hair",
        "Animal hair, fur, coats and manes",
        "Feathers and plumage as animal bodily coverings",
        "Mythological, symbolic and allegorical animals",
        "Descriptions of hair or bodily covering colour even when "
        "the creature is fictional",
        "Flaxen or similarly pale hair, recorded separately from white hair",
    ],
    exclude=[
        "White garments, clothing and robes",
        "White fabric, wool as a material, silk and textiles",
        "White paint, stone, buildings and other objects",
        "White light, radiance and luminous bodies without a hair "
        "or bodily-covering description",
        "White complexion or skin without a relevant hair or "
        "bodily-covering description",
    ],
)


def create_researcher_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set")

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0,
        max_retries=2,
        max_tokens=2048,
        model_kwargs={
            "response_format": {
                "type": "json_object"
            }
        },
    )


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

classification must be one of:
- relevant
- ambiguous
- irrelevant

feature_type must be one of:
- human_hair
- animal_fur
- feathers
- flaxen_hair
- other
- uncertain

Rules:
- Human hair is the primary category.
- Animal hair and fur, including mythological creatures, are secondary.
- Feathers and plumage are secondary and distinct from hair.
- Flaxen hair is secondary; do not automatically equate flaxen with white.
- Clothing, textiles, materials, objects, light and complexion alone
  are not hair or bodily-covering descriptions.
- Classify what the passage actually describes.
- Do not infer historical influence or transmission.
- Use the exact passage IDs supplied.
- Give a very brief reason, preferably under 10 words.

Return only valid JSON in this form:
{"classifications":[{"passage_id":"P001","classification":"relevant","feature_type":"human_hair","reason":"Describes white human scalp hair."}]}
"""

    instructions = {
        "search_term": config.search_term,
        "target_description": config.target_description,
        "include": config.include,
        "exclude": config.exclude,
        "retain_ambiguous": config.retain_ambiguous,
    }

    # Assign short IDs and retain the original IDs locally.
    id_map = {}
    prepared = []

    for index, passage in enumerate(passages, start=1):
        short_id = f"P{index:03d}"
        id_map[short_id] = passage["id"]

        prepared.append({
            "passage_id": short_id,
            "pub_year": passage.get("pub_year"),
            "title": passage.get("title"),
            "author": passage.get("author"),
            "text": (passage.get("text") or "")[:500],
        })

    def make_messages(batch: list[dict]) -> list[tuple[str, str]]:
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

    def estimate_tokens(messages: list[tuple[str, str]]) -> int:
        raw_tokens = sum(
            len(encoding.encode(content))
            for _, content in messages
        )

        return int(
            raw_tokens * TOKEN_SAFETY_MULTIPLIER
        ) + TOKEN_OVERHEAD

    # Greedily construct batches that fit the local budget.
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

        estimated = estimate_tokens(make_messages(current_batch))

        if estimated > MAX_ESTIMATED_TOKENS:
            raise ValueError(
                f"Passage {passage['passage_id']} alone exceeds "
                f"the estimated request budget ({estimated} tokens)."
            )

    if current_batch:
        batches.append(current_batch)

    logger.info(
        "LLM classification: %d passages in %d batches",
        len(prepared),
        len(batches),
    )

    all_classifications = []

    # Send each batch only after its size has been checked.
    for batch_number, batch in enumerate(batches, start=1):
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

            
    expected_ids = {p["passage_id"] for p in batch}
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
            f"Batch {batch_number} ID validation failed:\n"
            f"Unexpected: {sorted(unexpected)}\n"
            f"Duplicates: {duplicates}"
        )

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

        retry_messages = make_messages(missing_passages)

        logger.info(
            "Retrying %d omitted passages individually",
            len(missing_passages),
        )

        retry_response = llm.invoke(retry_messages)

        retry_result = ClassificationResult.model_validate(
            json.loads(retry_response.content)
        )

        retry_ids = [
            item.passage_id
            for item in retry_result.classifications
        ]

        retry_counts = Counter(retry_ids)

        retry_expected = {
            passage["passage_id"]
            for passage in missing_passages
        }

        retry_missing = retry_expected - set(retry_ids)
        retry_unexpected = set(retry_ids) - retry_expected
        retry_duplicates = {
            key: count
            for key, count in retry_counts.items()
            if count > 1
        }

        if retry_missing or retry_unexpected or retry_duplicates:
            raise ValueError(
                f"Retry validation failed:\n"
                f"Missing: {sorted(retry_missing)}\n"
                f"Unexpected: {sorted(retry_unexpected)}\n"
                f"Duplicates: {retry_duplicates}"
            )

        result.classifications.extend(
            retry_result.classifications
        )

    for item in result.classifications:
        item.passage_id = id_map[item.passage_id]
        all_classifications.append(item)

    return ClassificationResult(
        classifications=all_classifications
    )

