# src/diachronic_agents/retrieval/prospect_selector.py

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from diachronic_agents.llm.passage_classifier import ClassificationResult


FEATURE_PRIORITY = (
    "human_hair",
    "complexion",
    "animal_fur",
    "feathers",
    "flaxen_hair",
    "other",
    "uncertain",
)


def select_prospects(
    passages: list[dict[str, Any]],
    classification_result: ClassificationResult,
    *,
    feature_types: Iterable[str] | None = None,
    per_feature_limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Join LLM classifications to retrieved passages and select
    document-diverse research prospects.

    Selection is performed independently for each feature type.
    Within each feature type, the highest-ranked passage from
    each document is retained.

    Args:
        passages:
            Original passage dictionaries returned by retrieval.
        classification_result:
            Result from classify_passages().
        feature_types:
            Feature categories to retain. None means all categories.
        per_feature_limit:
            Maximum number of selected passages per feature type.
            None means no limit.

    Returns:
        Copies of selected passage dictionaries, enriched with
        classification metadata.
    """
    if per_feature_limit is not None and per_feature_limit < 1:
        raise ValueError("per_feature_limit must be at least 1 or None")

    passages_by_id = {
        passage["passage_id"]: passage
        for passage in passages
    }

    allowed_features = (
        set(feature_types)
        if feature_types is not None
        else None
    )

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_classification_ids: set[str] = set()

    for classification in classification_result.classifications:
        passage_id = classification.passage_id

        if passage_id in seen_classification_ids:
            raise ValueError(
                f"Duplicate classification for passage {passage_id}"
            )
        seen_classification_ids.add(passage_id)

        if passage_id not in passages_by_id:
            raise ValueError(
                f"Classification refers to unknown passage {passage_id}"
            )

        if classification.classification != "relevant":
            continue

        feature_type = classification.feature_type

        if allowed_features is not None and feature_type not in allowed_features:
            continue

        passage = passages_by_id[passage_id]

        # Keep the original passage intact; enrich a copy.
        prospect = {
            **passage,
            "classification": classification.classification,
            "feature_type": feature_type,
            "classification_reason": classification.reason,
        }

        candidates[feature_type].append(prospect)

    selected: list[dict[str, Any]] = []

    feature_order = [
        feature
        for feature in FEATURE_PRIORITY
        if feature in candidates
    ]

    # Include any future feature types without requiring this
    # function to be updated.
    feature_order.extend(
        sorted(set(candidates) - set(feature_order))
    )

    for feature_type in feature_order:
        feature_candidates = candidates[feature_type]

        # Lower retrieval rank is better. Preserve input order
        # when rank is unavailable or tied.
        feature_candidates = sorted(
            enumerate(feature_candidates),
            key=lambda item: (
                item[1].get("rank", float("inf")),
                item[0],
            ),
        )

        selected_documents: set[tuple[str, str]] = set()
        selected_for_feature = 0

        for _, prospect in feature_candidates:
            document_key = (
                prospect.get("corpus", ""),
                prospect.get("doc_id", prospect["passage_id"]),
            )

            if document_key in selected_documents:
                continue

            selected_documents.add(document_key)
            selected.append(prospect)
            selected_for_feature += 1

            if (
                per_feature_limit is not None
                and selected_for_feature >= per_feature_limit
            ):
                break

    return selected
