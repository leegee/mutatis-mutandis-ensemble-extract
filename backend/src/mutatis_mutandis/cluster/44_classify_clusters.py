#!/usr/bin/env python

"""
44_classify_clusters.py - interpret sampled clusters using Groq.

Selects nearest-to-centre or random exemplars from target_cluster_summary,
retrieves their passages from Postgres, sends the passages TOGETHER to Groq,
and stores one general interpretation per cluster in
target_cluster_interpretation.

Examples:

    # Interpret cluster 4 using 8 nearest exemplars
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters --cluster 4

    # Use random exemplars instead
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters --cluster 4 --sample

    # Several clusters
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters \
        --cluster 4 --cluster 7 --cluster 12 --n 15

    # Ten largest clusters
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters \
        --top 10 --n 8

    # Inspect the passages and prompt without calling Groq
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters \
        --cluster 4 --dry-run

    # Reinterpret existing clusters
    uv run python -m mutatis_mutandis.cluster.44_classify_clusters \
        --cluster 4 --force

Environment:
    GROQ_API_KEY

Overview:

    SELECT
        run_id,
        cluster,
        classification->>'category' AS category,
        classification->>'description' AS description
    FROM target_cluster_interpretation
    WHERE run_id = 'l8-target-form-20261118-083730'
    AND prompt_version = 'cluster-interpretation-v1'
    ORDER BY cluster;

"""

from __future__ import annotations

from collections import deque
from typing import Any
import argparse
import json
import math
import os
import time

from groq import Groq
import tiktoken

from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import logger


MODEL = "openai/gpt-oss-20b"
PROMPT_VERSION = "cluster-interpretation-v1"

DEFAULT_TPM_BUDGET = 6000
DEFAULT_MAX_COMPLETION_TOKENS = 500


CLASSIFICATION_SCHEMA = {
    "name": "cluster_interpretation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
            },
            "description": {
                "type": "string",
            },
            "evidence": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": [
            "category",
            "description",
            "evidence",
        ],
        "additionalProperties": False,
    },
}


SYSTEM_PROMPT = """
You are interpreting clusters of passages from a historical text corpus.

Your task is to identify the GENERAL SUBJECT or THEME shared by the
supplied passages.

You are classifying a cluster, NOT individual search results.

Read all the passages together and identify what they are generally
about. Give the cluster a concise, informative category and a short
description.

Important principles:

1. Classify the shared subject or theme of the passages, not merely
   the word that was used to retrieve them.

2. Look for what the passages are actually discussing: for example,
   divine and supernatural brightness, human hair colour, complexion,
   animal coloration, physical illumination, or intellectual brilliance.

3. Do not force a cluster into a predetermined research category.
   The passages may concern something outside the research subject.

4. Do not assume that every passage has exactly the same meaning.
   Identify the strongest common theme, but acknowledge significant
   variation where necessary.

5. If the passages do not form a coherent group, say so. A category
   such as "Mixed or incoherent cluster" is acceptable.

6. Distinguish the subject of a passage from its literary or rhetorical
   technique. You do not need to classify passages as literal,
   metaphorical, symbolic, simile, or visionary.

7. Do not diagnose individuals or infer albinism.

8. Do not use author, title or date to override the actual content.
   Bibliographic information is supplied to help identify the evidence.

9. The category should be short and meaningful. Avoid generic labels
   such as "Uses of brightness" when a more informative description
   is possible, such as "Divine and supernatural brightness".

10. The description should explain the shared theme in one or two
    sentences, not provide a separate analysis of every passage.

Evidence:
- Select two to four representative passages from the supplied sample.
- Quote only wording actually present in the passages.
- Identify each quotation by author and date where available.
- Evidence should support the cluster-level interpretation.

Return one JSON object with exactly these fields:

{
  "category": "A concise general category",
  "description": "A short explanation of the shared theme.",
  "evidence": [
    "Author (date): exact quotation from the passage."
  ]
}

Return JSON only. Do not use Markdown fences.
""".strip()


def _json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def token_count(text: str) -> int:
    """Estimate tokens using the encoding used in the earlier experiment."""
    try:
        return len(tiktoken.get_encoding("o200k_base").encode(text))
    except Exception:
        return math.ceil(len(text) / 4)


class TokenWindow:
    """Simple rolling-window TPM limiter."""

    def __init__(self, budget: int, window_seconds: int = 60):
        self.budget = budget
        self.window_seconds = window_seconds
        self.events: deque[tuple[float, int]] = deque()

    def wait(self, reserve: int) -> None:
        if reserve > self.budget:
            raise ValueError(
                f"Estimated request size ({reserve}) exceeds "
                f"TPM budget ({self.budget}). Reduce sample size or max tokens."
            )

        while True:
            now = time.monotonic()
            cutoff = now - self.window_seconds

            while self.events and self.events[0][0] <= cutoff:
                self.events.popleft()

            used = sum(tokens for _, tokens in self.events)

            if used + reserve <= self.budget:
                return

            if not self.events:
                continue

            wait_seconds = (
                self.events[0][0] + self.window_seconds - now
            )

            logger.info(
                f"  TPM limiter: {used}/{self.budget} tokens used; "
                f"waiting {wait_seconds:.1f}s"
            )

            time.sleep(max(0.25, wait_seconds))

    def record(self, tokens: int) -> None:
        self.events.append((time.monotonic(), max(1, tokens)))


def ensure_table(cur) -> None:
    """Create the cluster-level interpretation table."""

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS target_cluster_interpretation (
            run_id TEXT NOT NULL,
            cluster INTEGER NOT NULL,
            prompt_version TEXT NOT NULL,

            sample_kind TEXT NOT NULL,
            sample_size INTEGER NOT NULL,
            sample_occurrence_ids JSONB NOT NULL,
            samples JSONB NOT NULL,

            classification JSONB NOT NULL,
            raw_response TEXT NOT NULL,

            model TEXT NOT NULL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (run_id, cluster, prompt_version)
        )
        """
    )


def latest_run(cur) -> str:
    cur.execute(
        """
        SELECT run_id
        FROM target_projection_run
        ORDER BY created_at DESC
        LIMIT 1
        """
    )

    row = cur.fetchone()

    if not row:
        raise SystemExit("No runs found in target_projection_run")

    return row[0]


def selected_clusters(
    cur,
    run_id: str,
    requested: list[int],
    top: int,
) -> list[int]:

    clusters = list(dict.fromkeys(requested))

    if top:
        cur.execute(
            """
            SELECT cluster
            FROM target_cluster_summary
            WHERE run_id = %s
              AND cluster >= 0
            ORDER BY n DESC
            LIMIT %s
            """,
            (run_id, top),
        )

        clusters.extend(
            cluster
            for (cluster,) in cur.fetchall()
            if cluster not in clusters
        )

    if not clusters:
        raise SystemExit(
            "Specify at least one --cluster or use --top."
        )

    return clusters


def get_sample_ids(
    cur,
    run_id: str,
    cluster: int,
    n: int,
    sample: bool,
) -> list[str]:

    cur.execute(
        """
        SELECT nearest, sample
        FROM target_cluster_summary
        WHERE run_id = %s
          AND cluster = %s
        """,
        (run_id, cluster),
    )

    row = cur.fetchone()

    if not row:
        logger.info(f"Cluster {cluster}: no summary found")
        return []

    nearest, random_sample = row
    ids = _json(random_sample if sample else nearest) or []

    return [str(oid) for oid in ids[:n]]


def get_occurrence_metadata(
    cur,
    occurrence_ids: list[str],
) -> dict[str, tuple]:

    if not occurrence_ids:
        return {}

    cur.execute(
        """
        SELECT
            o.occurrence_id,
            o.corpus,
            o.doc_id,
            o.pub_year,
            o.hit_idx,
            d.author,
            d.title
        FROM target_occurrence o
        LEFT JOIN documents d
          ON d.corpus = o.corpus
         AND d.doc_id = o.doc_id
        WHERE o.occurrence_id = ANY(%s)
        """,
        (occurrence_ids,),
    )

    return {
        str(row[0]): row
        for row in cur.fetchall()
    }


def get_passage(
    cur,
    corpus: str,
    doc_id: str,
    hit_idx: int,
    words: int,
) -> str:
    """Retrieve a passage and mark the target token."""

    cur.execute(
        """
        SELECT token_idx, token
        FROM tokens
        WHERE corpus = %s
          AND doc_id = %s
          AND token_idx BETWEEN %s AND %s
        ORDER BY token_idx
        """,
        (corpus, doc_id, hit_idx - words, hit_idx + words),
    )

    parts = []

    for idx, token in cur.fetchall():
        if idx == hit_idx:
            parts.append(f"[[TARGET]]{token}[[/TARGET]]")
        else:
            parts.append(str(token))

    return " ".join(parts)


def already_interpreted(
    cur,
    run_id: str,
    cluster: int,
) -> bool:

    cur.execute(
        """
        SELECT 1
        FROM target_cluster_interpretation
        WHERE run_id = %s
          AND cluster = %s
          AND prompt_version = %s
        """,
        (run_id, cluster, PROMPT_VERSION),
    )

    return cur.fetchone() is not None


def make_samples(
    cur,
    occurrence_ids: list[str],
    metadata_by_id: dict[str, tuple],
    words: int,
) -> list[dict]:

    samples = []

    for occurrence_id in occurrence_ids:
        metadata = metadata_by_id.get(occurrence_id)

        if not metadata:
            logger.info(f"  Missing occurrence: {occurrence_id}")
            continue

        (
            _,
            corpus,
            doc_id,
            year,
            hit_idx,
            author,
            title,
        ) = metadata

        passage_text = get_passage(
            cur,
            corpus,
            doc_id,
            hit_idx,
            words,
        )

        if not passage_text:
            logger.info(f"  Empty passage: {occurrence_id}")
            continue

        samples.append({
            "occurrence_id": occurrence_id,
            "corpus": corpus,
            "doc_id": doc_id,
            "year": year,
            "author": author,
            "title": title,
            "passage": passage_text,
        })

    return samples


def make_user_prompt(samples: list[dict]) -> str:

    parts = [
        "Interpret the following cluster of historical passages.",
        "Read them together and identify their general shared theme.",
        "",
    ]

    for i, sample in enumerate(samples, start=1):
        author = sample.get("author") or "Unknown author"
        year = sample.get("year") or "Date unknown"
        title = sample.get("title") or sample.get("doc_id") or "Untitled"

        parts.extend([
            f"PASSAGE {i}",
            f"Author: {author}",
            f"Date: {year}",
            f"Work: {title}",
            sample["passage"],
            "",
        ])

    return "\n".join(parts)


def validate_interpretation(data: dict) -> dict:
    """Check and normalise the model's cluster-level response."""

    if not isinstance(data, dict):
        raise ValueError("Model response is not a JSON object")

    category = str(data.get("category", "")).strip()
    description = str(data.get("description", "")).strip()
    evidence = data.get("evidence", [])

    if not category:
        raise ValueError("Missing cluster category")

    if not description:
        raise ValueError("Missing cluster description")

    if not isinstance(evidence, list):
        raise ValueError("Evidence must be a list")

    evidence = [
        str(item).strip()
        for item in evidence
        if str(item).strip()
    ]

    return {
        "category": category,
        "description": description,
        "evidence": evidence,
    }


def classify_with_groq(
    client: Groq,
    samples: list[dict],
    model: str,
    max_tokens: int,
    limiter: TokenWindow,
) -> tuple[dict, str, dict]:

    user_prompt = make_user_prompt(samples)

    combined_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    estimated_prompt_tokens = token_count(combined_prompt) + 50
    reserve = estimated_prompt_tokens + max_tokens

    limiter.wait(reserve)

    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": combined_prompt,
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": CLASSIFICATION_SCHEMA,
                },
                temperature=0,
                max_completion_tokens=max_tokens,
                reasoning_effort="low",
            )

            raw = response.choices[0].message.content or ""

            parsed = validate_interpretation(json.loads(raw))

            usage_obj = response.usage

            usage = {
                "prompt_tokens": getattr(
                    usage_obj, "prompt_tokens", None
                ),
                "completion_tokens": getattr(
                    usage_obj, "completion_tokens", None
                ),
                "total_tokens": getattr(
                    usage_obj, "total_tokens", None
                ),
            }

            actual_tokens = (
                usage["total_tokens"]
                if usage["total_tokens"] is not None
                else reserve
            )

            limiter.record(actual_tokens)

            return parsed, raw, usage

        except Exception as exc:
            status = getattr(exc, "status_code", None)
            retryable = status in {429, 500, 502, 503, 504}

            if not retryable or attempt == 4:
                raise

            headers = getattr(exc, "headers", {}) or {}
            retry_after = headers.get("retry-after")

            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = min(60, 5 * (2 ** attempt))

            logger.info(
                f"  Groq returned HTTP {status}; "
                f"retrying in {delay:.1f}s"
            )

            time.sleep(delay)

    raise RuntimeError("Groq retry loop exhausted")


def store_interpretation(
    cur,
    run_id: str,
    cluster: int,
    sample_kind: str,
    samples: list[dict],
    interpretation: dict,
    raw_response: str,
    model: str,
    usage: dict,
) -> None:

    occurrence_ids = [
        sample["occurrence_id"]
        for sample in samples
    ]

    cur.execute(
        """
        INSERT INTO target_cluster_interpretation (
            run_id,
            cluster,
            prompt_version,
            sample_kind,
            sample_size,
            sample_occurrence_ids,
            samples,
            classification,
            raw_response,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s::jsonb, %s::jsonb, %s::jsonb, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (run_id, cluster, prompt_version)
        DO UPDATE SET
            sample_kind = EXCLUDED.sample_kind,
            sample_size = EXCLUDED.sample_size,
            sample_occurrence_ids = EXCLUDED.sample_occurrence_ids,
            samples = EXCLUDED.samples,
            classification = EXCLUDED.classification,
            raw_response = EXCLUDED.raw_response,
            model = EXCLUDED.model,
            prompt_tokens = EXCLUDED.prompt_tokens,
            completion_tokens = EXCLUDED.completion_tokens,
            total_tokens = EXCLUDED.total_tokens,
            updated_at = NOW()
        """,
        (
            run_id,
            cluster,
            PROMPT_VERSION,
            sample_kind,
            len(samples),
            json.dumps(occurrence_ids),
            json.dumps(samples, ensure_ascii=False),
            json.dumps(interpretation, ensure_ascii=False),
            raw_response,
            model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
        ),
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0]
    )

    parser.add_argument("--run-id", default=None)

    parser.add_argument(
        "--cluster",
        type=int,
        action="append",
        default=[],
        help="Cluster ID; repeatable. Use -1 for noise.",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="Interpret samples from the N largest clusters.",
    )

    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--words", type=int, default=30)

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use random members instead of nearest-to-centre.",
    )

    parser.add_argument("--model", default=MODEL)

    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
    )

    parser.add_argument(
        "--tpm-budget",
        type=int,
        default=DEFAULT_TPM_BUDGET,
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Reinterpret existing cluster records.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show passages and prompt without calling Groq.",
    )

    args = parser.parse_args()

    if args.n < 1:
        raise SystemExit("--n must be at least 1")

    if args.words < 1:
        raise SystemExit("--words must be at least 1")

    if not args.dry_run and not os.getenv("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY environment variable is missing")

    client = None if args.dry_run else Groq(
        api_key=os.environ["GROQ_API_KEY"]
    )

    limiter = TokenWindow(args.tpm_budget)
    sample_kind = "random" if args.sample else "nearest"

    conn = get_connection(
        application_name="classify-clusters"
    )

    interpreted = 0
    skipped = 0
    failed = 0

    try:
        with conn.cursor() as cur:

            ensure_table(cur)
            conn.commit()

            run_id = args.run_id or latest_run(cur)

            clusters = selected_clusters(
                cur,
                run_id,
                args.cluster,
                args.top,
            )

            logger.info(f"Run: {run_id}")
            logger.info(f"Model: {args.model}")
            logger.info(f"Sample type: {sample_kind}")
            logger.info(f"Prompt version: {PROMPT_VERSION}")
            logger.info(f"TPM budget: {args.tpm_budget:,}")
            logger.info(f"Clusters: {clusters}")

            for cluster in clusters:

                if (
                    not args.force
                    and not args.dry_run
                    and already_interpreted(cur, run_id, cluster)
                ):
                    logger.info(
                        f"\nCluster {cluster}: cached; skipping"
                    )
                    skipped += 1
                    continue

                ids = get_sample_ids(
                    cur,
                    run_id,
                    cluster,
                    args.n,
                    args.sample,
                )

                if not ids:
                    logger.info(
                        f"Cluster {cluster}: no samples available"
                    )
                    continue

                metadata_by_id = get_occurrence_metadata(cur, ids)

                samples = make_samples(
                    cur,
                    ids,
                    metadata_by_id,
                    args.words,
                )

                if not samples:
                    logger.info(
                        f"Cluster {cluster}: no usable passages"
                    )
                    failed += 1
                    continue

                logger.info(
                    f"\nCluster {cluster}: "
                    f"{len(samples)} passages supplied together"
                )

                for i, sample in enumerate(samples, start=1):
                    logger.info(
                        f"\n  Passage {i}: "
                        f"[{sample['year']}] "
                        f"{sample['author'] or '?'}, "
                        f"{sample['title'] or sample['doc_id']}"
                    )
                    logger.info(f"  {sample['passage']}")

                user_prompt = make_user_prompt(samples)

                if args.dry_run:
                    combined_prompt = (
                        f"{SYSTEM_PROMPT}\n\n{user_prompt}"
                    )
                    logger.info(
                        f"\n  Estimated prompt tokens: "
                        f"{token_count(combined_prompt)}"
                    )
                    logger.info(
                        f"  Completion token allowance: "
                        f"{args.max_tokens}"
                    )
                    continue

                try:
                    interpretation, raw, usage = classify_with_groq(
                        client,
                        samples,
                        args.model,
                        args.max_tokens,
                        limiter,
                    )

                    store_interpretation(
                        cur,
                        run_id,
                        cluster,
                        sample_kind,
                        samples,
                        interpretation,
                        raw,
                        args.model,
                        usage,
                    )

                    conn.commit()

                    logger.info(
                        f"\n  Category: {interpretation['category']}"
                    )
                    logger.info(
                        f"  Description: {interpretation['description']}"
                    )

                    for evidence in interpretation["evidence"]:
                        logger.info(f"  Evidence: {evidence}")

                    logger.info(
                        f"  Tokens: {usage.get('total_tokens')}"
                    )

                    interpreted += 1

                except Exception:
                    conn.rollback()
                    logger.exception(
                        f"  Cluster {cluster}: interpretation failed"
                    )
                    failed += 1

            logger.info("\nInterpretation complete")
            logger.info(f"  Interpreted: {interpreted}")
            logger.info(f"  Cached/skipped: {skipped}")
            logger.info(f"  Failed: {failed}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()